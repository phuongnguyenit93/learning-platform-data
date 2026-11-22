# Kiểm thử schema validation và các phiên bản dữ liệu cùng tồn tại

Một dịch vụ Java quản lý danh mục sản phẩm lưu dữ liệu trong MongoDB. Những document cũ chứa `title` và `priceVnd`; một phiên bản ứng dụng mới đổi sang `name` và đối tượng `price`, đồng thời thêm `schemaVersion: 2`. Khi triển khai rolling, một số instance vẫn chạy mã cũ, một số instance đã chạy mã mới. Hệ thống còn có batch job ghi dữ liệu cũ, event từ queue được phát lại và các document chưa kịp backfill. Một hôm, lỗi xuất hiện: ứng dụng mới đọc document v1 trả giá bằng `0`; ứng dụng cũ ghi đè document v2 làm mất field mới; một API PATCH cập nhật thiếu field bắt buộc nhưng validator vẫn không chặn vì cấu hình đang ở chế độ cho phép cảnh báo.

Bài toán không chỉ là định nghĩa một JSON Schema. Đây là **kiểm thử tính đúng khi nhiều phiên bản dữ liệu và nhiều phiên bản phần mềm cùng hoạt động**: dữ liệu nào được phép tồn tại, reader nào phải đọc được phiên bản nào, writer nào được phép tạo ra định dạng nào, bản ghi phải giữ những bất biến nào sau CREATE/UPDATE/UPSERT/DELETE, và lúc nào có thể loại bỏ hỗ trợ phiên bản cũ.

Bài học thuộc chương **Kiểm thử tính đúng**, module **Database No SQL**. Ta sẽ kết hợp **schema validation ở database, validation trong ứng dụng, serialization/contract tests, compatibility matrix, migration/backfill, concurrency và dữ liệu lỗi có chủ đích** để chứng minh hệ không âm thầm đọc sai, ghi đè mất fields hoặc từ chối dữ liệu hợp lệ khi triển khai từng phần.

> **Nguyên tắc:** “Document hợp lệ với schema hiện tại” và “document đọc/ghi đúng trong suốt quá trình nâng cấp” là **hai mệnh đề khác nhau**. Muốn hệ đúng, phải kiểm thử cả trạng thái ổn định lẫn các trạng thái chuyển tiếp.

Các ví dụ là tài liệu học tập, không phải cấu hình áp dụng trực tiếp vào production. Khả năng và tên tham số validator phụ thuộc database/version/deployment; cần đối chiếu hợp đồng engine cụ thể khi triển khai.

## 1. Schema trong NoSQL không có nghĩa chỉ một dạng JSON

Tùy mô hình NoSQL:

- **Document:** hình dạng các fields, kiểu BSON/JSON, nested objects, arrays, validation rules, indexes, collation.
- **Key-value:** định dạng bytes/JSON/Protobuf, key namespace, TTL, serialization version, những ý nghĩa do ứng dụng xác định.
- **Wide-column:** keyspace/table/column types, partition/clustering keys, schema agreement, TTL và data-model contract.
- **Graph:** kiểu nodes/edges/properties, ràng buộc nghiệp vụ và phiên bản cách biểu diễn quan hệ.
- **Managed key-value/document:** key schema/indexes do dịch vụ kiểm, nhưng nhiều fields khác được kiểm ở application layer.

Một NoSQL database có thể chấp nhận documents không đồng nhất mà **không hề bảo đảm mọi reader hiểu đúng chúng**. Schema cần xét từ dữ liệu trên đĩa đến API và nghiệp vụ.

## 2. Ba lớp validation và trách nhiệm

| Lớp | Kiểm soát được | Thường không đủ để kiểm |
|---|---|---|
| **Database/storage validator** | Field type, required, allowed values, document shape; constraints trong phạm vi engine | Quy tắc liên document, toàn bộ authz, các version reader thực hỗ trợ |
| **Application/domain validator** | Business invariants, authorization scope, phép biến đổi, command semantics | Mọi writer bypass service hoặc command admin |
| **Serialization/contract validator** | Giải mã v1/v2/v3, API/event compatibility, type mapping | Atomic writes, uniqueness toàn cụm, dữ liệu đã persist đúng ở DB |

Phải test **từng lớp** và **đường tương tác giữa chúng**. Nếu API chặn đầu vào nhưng một batch job ghi trực tiếp DB, dữ liệu sai vẫn có thể xuất hiện nếu DB không chặn. Nếu DB chấp nhận document v1 nhưng Java reader không còn hỗ trợ, ứng dụng vẫn lỗi.

## 3. Ví dụ chạy xuyên suốt: ba dạng Product

**Version 1 — legacy, không có trường `schemaVersion`:**

~~~json
{
  "_id": "p-101",
  "title": "Bàn gỗ",
  "priceVnd": 125000,
  "active": true,
  "revision": 4
}
~~~

**Version 2 — định dạng mới:**

~~~json
{
  "_id": "p-101",
  "schemaVersion": 2,
  "name": "Bàn gỗ",
  "price": {
    "amountVnd": 125000,
    "currency": "VND"
  },
  "lifecycle": "ACTIVE",
  "revision": 5
}
~~~

**Version 3 — mở rộng dữ liệu phân loại:**

~~~json
{
  "_id": "p-101",
  "schemaVersion": 3,
  "name": "Bàn gỗ",
  "price": {
    "amountVnd": 125000,
    "currency": "VND"
  },
  "lifecycle": "ACTIVE",
  "tags": ["furniture", "indoor"],
  "revision": 6
}
~~~

Ví dụ giả định `amountVnd` là số nguyên VND, không phải phép tính chuyển đơn vị tiền có phần thập phân. Production phải định nghĩa rõ loại số, đơn vị, giới hạn và quy tắc làm tròn theo nghiệp vụ.

## 4. Phiên bản dữ liệu khác phiên bản cập nhật

Phân biệt:

- `schemaVersion`: document được mã hóa theo contract v1/v2/v3 nào.
- `revision`: phiên bản **một thực thể** sau mỗi business mutation, dùng kiểm concurrency.
- `eventVersion`: phiên bản của event envelope.
- `applicationVersion`: binary/release đang chạy.
- `migrationVersion`: trạng thái đã chạy các bước nâng schema ở database.
- `CDC position`: vị trí opaque trong change stream, không tự là business version.

Một product có thể ở `schemaVersion=2` qua 100 cập nhật, với `revision` tăng từ 5 đến 105. Không được dùng `schemaVersion` để phát hiện lost update. Ngược lại, `revision=100` không chứng minh document thuộc schema nào.

## 5. Dữ liệu cũ không có version phải được định nghĩa rõ

Một số hệ đã có hàng triệu records trước khi thêm `schemaVersion`. Có thể chọn:

~~~text
Nếu schemaVersion absent và document phù hợp cấu trúc legacy:
  đọc như v1.
Nếu schemaVersion == 2:
  đọc như v2.
Nếu schemaVersion == 3:
  đọc như v3.
Nếu schemaVersion null, chuỗi "2", số 4 hoặc invalid:
  trả lỗi dữ liệu có kiểm soát.
~~~

Không tự xem **null** và **absent** là giống nhau. Cũng không suy v1 từ việc thiếu `name` nếu document có thể là bản v2 bị ghi hỏng.

Kiểm thử cần có cả legacy unversioned fixtures, explicit supported versions và unsupported/corrupt versions.

## 6. “Hợp lệ” phải xác định theo loại thao tác

Các câu hỏi khác nhau:

- **Create:** writer có được phép tạo mới v1 khi v2 đã là chuẩn không?
- **Full replace:** mất fields cũ/mới có bị phát hiện không?
- **Partial update:** sau PATCH, toàn bộ document còn hợp lệ không?
- **Upsert:** đường update và đường insert có tạo cùng schema không?
- **Read:** reader có giải mã mọi version cam kết hỗ trợ không?
- **Delete:** có giữ semantics tombstone/TTL/retention đúng không?
- **Backfill:** chuyển v1→v2 có idempotent và bảo toàn giá trị không?
- **CDC replay:** event cũ có làm document mới thụt lùi không?
- **Restore:** schema, validator và application release có tương thích recovery point không?

Chỉ test POST hợp lệ không chứng minh schema validation hoạt động cho các thao tác còn lại.

## 7. Định nghĩa các bất biến nghiệp vụ trước khi chọn validator

Ví dụ Product:

1. Mã sản phẩm `_id` không rỗng và không bị đổi sau khi tạo.
2. Giá `amountVnd` là số nguyên không âm theo giới hạn đã xác định.
3. `currency == "VND"` cho catalog này.
4. Lifecycle thuộc tập `ACTIVE`, `PAUSED`, `ARCHIVED`.
5. V1 `title` và v2/v3 `name` tương ứng cùng tên nghiệp vụ.
6. Không tạo giá `0` như default khi thiếu/không giải mã được giá thật.
7. Tenant của product không thể bị sửa qua request không có quyền.
8. `revision` phải tăng đúng khi một business write thành công.
9. V3 `tags` là mảng chuỗi phù hợp giới hạn; không gây nổ kích thước document.
10. Product version không được tự thụt lùi vì một writer cũ.

Bất biến cần được thực thi ở **đúng ranh giới**: type/enum trong validator; uniqueness bằng index/conditional operation; authorization theo tenant ở service/DB policy; multi-record invariant bằng transaction hoặc giao thức riêng.

## 8. Ma trận hỗ trợ giữa readers và dữ liệu

Giả sử:

| Reader release | v1 legacy | v2 | v3 |
|---|---|---|---|
| R1 cũ | Có | Không bảo đảm | Không |
| R2 chuyển tiếp | Có | Có | Chỉ khi đã kiểm tương thích |
| R3 mở rộng | Có | Có | Có |
| R4 sau sunset v1 | Không, có lỗi rõ | Có | Có |

“Không bảo đảm” phải được hiểu là **không được cho nhận traffic loại dữ liệu ấy** trước khi thực nghiệm chứng minh tương thích. Không mặc định reader có thể bỏ qua field lạ thì sẽ an toàn: nó có thể ghi lại document và **làm mất field lạ**.

Mỗi ô “Có” trong ma trận cần test bằng fixture và operation cụ thể, không chỉ kiểm deserialize không ném exception.

## 9. Ma trận writers và định dạng đầu ra

| Writer | Định dạng tạo mới | Có thể cập nhật document nào? |
|---|---|---|
| W1 cũ | v1 | Chỉ v1, nếu route/protocol cho phép |
| W2 chuyển tiếp | v2 | v1/v2 theo migration policy |
| W3 mới | v3 | v1/v2/v3 theo tested adapter |
| Background backfill | v2 hoặc v3 | Chỉ khi có source-version guard |
| CDC consumer | Theo schema target | Theo ordering và idempotency contract |

Mục tiêu của rollout an toàn là **không để W1 ghi đè v2/v3**. Ngay cả khi R1 có thể đọc được vài field chung của v2, việc nó full-replace document có thể làm mất các field W2/W3 đã thêm.

## 10. Backward compatibility, forward compatibility và full compatibility

Cần nói rõ chiều của câu hỏi:

- **New reader đọc old data:** khả năng đọc ngược dữ liệu cũ (backward data compatibility).
- **Old reader đọc new data:** khả năng đọc xuôi dữ liệu mới (forward data compatibility).
- **Old writer cập nhật new data:** write compatibility, khó hơn khả năng đọc.
- **New writer phát events cho old consumers:** event forward compatibility.
- **Reader đọc nhiều versions cùng lúc:** mixed-version support.

Ví dụ:
~~~text
R2 đọc được v1 và v2.
W2 tạo v2.
R1 không đọc được v2.
~~~

Nếu triển khai W2 trước khi thay hết R1, request chạy vào R1 có thể fail. Giải pháp thường là **mở rộng readers trước, rồi đổi writers**, không đồng thời đổi cả hai tùy ý.

## 11. Expand – migrate – contract

~~~mermaid
flowchart LR
    A["V1 stable"] --> B["Expand readers/validators để hiểu v1+v2"]
    B --> C["Deploy writers v2 có kiểm soát"]
    C --> D["Backfill v1 -> v2 có checkpoint"]
    D --> E["Reconcile/verify không còn v1"]
    E --> F["Contract: chặn writer v1, thu hẹp validator"]
    F --> G["V2 stable"]
~~~

Ở giai đoạn expand, dữ liệu cũ vẫn tồn tại. Giai đoạn contract chỉ được bắt đầu sau khi chứng minh:
- Không còn bản ghi cũ trong các vùng thuộc phạm vi.
- Không còn old producers, batch jobs, CDC/retry replay tạo định dạng cũ.
- Readers cũ đã được loại bỏ hoặc được định tuyến an toàn.
- Backup/restore còn yêu cầu đọc v1 hay không đã có kế hoạch.
- Business metrics và error budgets đạt.

**Không thu hẹp validator trước khi quá trình chuyển dữ liệu và nguồn ghi cũ hoàn toàn được xử lý.**

## 12. MongoDB: validation ở collection khác JSON Schema của ứng dụng

MongoDB có collection validators, có thể sử dụng toán tử `$jsonSchema` với những keyword và kiểu dữ liệu BSON được hệ hỗ trợ. Nó kiểm tra documents khi ghi theo cấu hình.

Ví dụ điều kiện:
- `bsonType`: kiểu dữ liệu BSON.
- `required`: các fields cần có.
- `properties`: mô tả fields và nested objects.
- `enum`: tập giá trị được phép.
- `minimum`: cận số.
- `additionalProperties`: xử lý fields ngoài schema khi thực sự muốn.

MongoDB không thay JSON Schema library tổng quát theo cùng một bộ keyword/version tuyệt đối. Cần kiểm **keyword support và kiểu BSON theo server version**. Đặc biệt `NumberInt`, `NumberLong`, `Double`, `Decimal128` không nên bị coi là cùng một dạng JavaScript Number nếu contract cần độ chính xác.

## 13. MongoDB: validator cho v2

Ví dụ trong `mongosh`, ở môi trường thử nghiệm:

~~~javascript
db.createCollection("products_v2_test", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["schemaVersion", "name", "price", "lifecycle", "revision"],
      properties: {
        schemaVersion: { enum: [2] },
        name: { bsonType: "string", minLength: 1 },
        price: {
          bsonType: "object",
          required: ["amountVnd", "currency"],
          properties: {
            amountVnd: { bsonType: ["int", "long"], minimum: 0 },
            currency: { enum: ["VND"] }
          }
        },
        lifecycle: { enum: ["ACTIVE", "PAUSED", "ARCHIVED"] },
        revision: { bsonType: ["int", "long"], minimum: 0 }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Tình huống minh họa:
- V2 đủ field và giá hợp lệ: được phép.
- Thiếu `price`: bị từ chối.
- `amountVnd: "125000"` chuỗi: bị từ chối.
- `lifecycle: "DELETED_FOREVER"`: bị từ chối.
- Giá âm: bị từ chối.

Validator trên **không bắt mọi quy tắc**: uniqueness phải có index, tenant authorization do layer được ủy quyền kiểm, các phép so liên document cần cơ chế khác.

## 14. MongoDB: validator chuyển tiếp cho v1 và v2

Trong giai đoạn migration, một collection có thể cần chấp nhận **cả unversioned v1 và explicit v2**. Ví dụ khái niệm:

~~~javascript
db.createCollection("products_mixed_test", {
  validator: {
    $or: [
      {
        $and: [
          { schemaVersion: { $exists: false } },
          { $jsonSchema: {
              bsonType: "object",
              required: ["title", "priceVnd", "active", "revision"],
              properties: {
                title: { bsonType: "string", minLength: 1 },
                priceVnd: { bsonType: ["int", "long"], minimum: 0 },
                active: { bsonType: "bool" },
                revision: { bsonType: ["int", "long"], minimum: 0 }
              }
          }}
        ]
      },
      {
        $jsonSchema: {
          bsonType: "object",
          required: ["schemaVersion", "name", "price", "lifecycle", "revision"],
          properties: {
            schemaVersion: { enum: [2] },
            name: { bsonType: "string", minLength: 1 },
            lifecycle: { enum: ["ACTIVE", "PAUSED", "ARCHIVED"] },
            revision: { bsonType: ["int", "long"], minimum: 0 },
            price: {
              bsonType: "object",
              required: ["amountVnd", "currency"],
              properties: {
                amountVnd: { bsonType: ["int", "long"], minimum: 0 },
                currency: { enum: ["VND"] }
              }
            }
          }
        }
      }
    ]
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Điểm cần lưu ý:
- Nhánh v1 yêu cầu `schemaVersion` **không tồn tại**; `null` không được coi là v1.
- Nhánh v2 bắt buộc explicit `schemaVersion: 2`.
- V3 chưa được cho phép trong ví dụ.
- Nếu muốn cấm cả những field dư, cần quy định `additionalProperties` cẩn thận, gồm `_id` và các fields hệ thống hợp lệ.
- Trong production, phải có kế hoạch cập nhật validator an toàn trên dữ liệu có sẵn và nhiều writers.

Validator dạng `$or` minh họa mixed-schema policy, không phải bằng chứng mọi tính năng của mọi MongoDB deployment đều giống nhau.

## 15. MongoDB: validationLevel và validationAction phải được kiểm thử

Phân biệt:

- `validationLevel: "strict"`: áp dụng validation cho inserts/updates theo semantics của engine.
- `validationLevel: "moderate"`: có chính sách khác khi cập nhật existing documents đã không hợp lệ; **không được mặc định hiểu là luôn kiểm mọi write**.
- `validationAction: "error"`: từ chối ghi vi phạm validator.
- `validationAction: "warn"`: cho phép ghi nhưng phát thông tin cảnh báo theo cơ chế của database.

Trong môi trường có dữ liệu legacy không hợp lệ, `moderate` hoặc `warn` có thể hữu ích theo kế hoạch chuyển tiếp **nhưng không đáp ứng yêu cầu “mọi dữ liệu mới đều bị cưỡng chế hợp lệ” nếu chưa xác minh chính xác behavior**.

Bài test nên xác nhận **persisted outcome**, không chỉ API return:
1. Insert dữ liệu sai.
2. Update document hợp lệ thành sai.
3. Update document vốn đã sai.
4. Chạy với từng mode.
5. Đọc lại database và kiểm log/counters theo khả năng quan sát.

## 16. MongoDB: quyền bypass validation

Một số lệnh/công cụ có cơ chế `bypassDocumentValidation` khi caller có quyền tương ứng. Điều này có thể cần trong import/repair, nhưng cũng là đường đưa dữ liệu sai vào production.

Cần test:
- Service account bình thường **không thể** bypass.
- Migration principal có quyền hạn được phê duyệt khi thực sự cần.
- Bypass mode có audit/TTL và scope.
- Dữ liệu nhập bypass được kiểm lại bằng validator/backfill.
- Sau migration, quyền bypass được thu hồi.
- Recovery từ backup không mặc nhiên được coi là toàn bộ documents đã qua validation.

**Collection validator không bảo vệ khi principal hợp lệ được phép đi vòng nó**; access control và change governance là một phần của correctness.

## 17. Missing, null, empty và sai kiểu là bốn tình huống

Cùng field `name`:

~~~json
{"schemaVersion":2}
{"schemaVersion":2,"name":null}
{"schemaVersion":2,"name":""}
{"schemaVersion":2,"name":19}
~~~

Nếu `required: ["name"]` chỉ kiểm field tồn tại, `null` có thể vẫn là present; phải thêm `bsonType: "string"`. String rỗng cần `minLength` hoặc business validator. Số 19 cần bị chặn bởi type checking.

Không tự biến:
~~~text
Missing price -> 0.
Invalid currency -> VND.
Unknown enum -> ACTIVE.
~~~

trong parser mà không có business policy, vì dữ liệu lỗi sẽ trở thành **giá hợp lệ giả**. Test phải xác minh parser fail rõ ràng hoặc quarantine record.

## 18. Numeric types và vấn đề chính xác

Các trường có thể trông giống nhau ở JSON:
~~~json
{"priceVnd":125000}
~~~

Nhưng BSON/source API có thể thể hiện bằng Int32, Int64, Double hoặc Decimal128. Khi đổi qua Java/JavaScript, cần test:
- Giá trị sát giới hạn kiểu 32-bit.
- Giá trị lớn hơn phạm vi biểu diễn nguyên chính xác của JavaScript Number.
- Decimal precision và rounding.
- Giá âm, số 0 và giá trị cực lớn.
- String `"125000"` từ import.
- NaN/Infinity nếu đường input có thể tạo và hệ hỗ trợ những giá trị ấy.
- Overflow khi cộng/nhân.
- Mismatch kiểu sau serialize/deserialize.

Nên định nghĩa **đơn vị và kiểu canonical** rõ ràng: ví dụ amount VND dạng nguyên 64-bit có phạm vi nghiệp vụ hợp lệ. Không để cùng một writer dùng Long và writer khác dùng Double mà chỉ dựa trên giá trị hiển thị tương đương.

## 19. Enum evolution không đơn giản là thêm giá trị

Giả sử v2 `lifecycle` chỉ có:
~~~text
ACTIVE, PAUSED, ARCHIVED
~~~

W3 thêm `DISCONTINUED`. Reader R2 có thể:
- Throw exception.
- Rơi vào default `ACTIVE` sai.
- Bỏ qua record.
- Hiển thị trạng thái không xác định.

Cần test từng behavior. Những hướng xử lý:
- Chặn W3 phát giá trị mới khi R2 còn chạy.
- Mở rộng readers hiểu unknown enum theo cách an toàn nếu business cho phép.
- Feature flag và traffic gating.
- Chỉ mở schema validator sau khi client compatibility được chứng minh.

Không tự map `DISCONTINUED` thành `ACTIVE` chỉ để tránh exception, vì đó là thay đổi nghĩa vụ nghiệp vụ.

## 20. Unknown fields: bỏ qua khi đọc có thể chấp nhận, xóa khi ghi thì không

V2 document:
~~~json
{
  "schemaVersion":2,
  "name":"Bàn gỗ",
  "price":{"amountVnd":125000,"currency":"VND"},
  "lifecycle":"ACTIVE",
  "metadata":{"origin":"supplier-import"}
}
~~~

Một reader chỉ cần `name`/`price` có thể bỏ qua metadata. Nhưng nếu nó deserialize vào DTO thiếu `metadata` rồi `replaceOne` toàn document, trường này biến mất.

Test cần phân biệt:
- **Read tolerant:** bỏ qua fields không hiểu.
- **Write preserving:** PATCH chỉ fields được phép sửa.
- **Full replacement:** bắt buộc document được xây với contract đầy đủ hoặc bị cấm cho writer cũ.
- **Unknown field policy:** khi nào từ chối để tránh payload injection?

Tolerant reader không tự trở thành compatible writer.

## 21. Nested objects và arrays có các trường hợp riêng

V3 `tags`:

~~~json
{"schemaVersion":3,"tags":["furniture","indoor"]}
~~~

Những trường hợp cần thử:
- `tags` missing.
- `tags: null`.
- `tags: []`.
- `tags` chứa `null`, số, object.
- Duplicate tags.
- Tags dài quá mức hoặc chuỗi rỗng.
- Nested object field lạ.
- Array thứ tự có/không ý nghĩa.
- Kích thước document vượt giới hạn.
- Backfill tag cũ theo quy tắc deterministic.

Database validator có thể kiểm array types/length tùy engine; nghiệp vụ có thể yêu cầu uniqueness và chuẩn hóa Unicode mà một validator đơn giản chưa đủ.

## 22. Partial update phải để toàn document còn hợp lệ

Một PATCH:

~~~javascript
db.products.updateOne(
  { _id: "p-101" },
  { $unset: { name: "" } }
);
~~~

Với validation nghiêm ngặt, document v2 sau cập nhật thiếu `name` cần bị từ chối. Nếu validator quá lỏng hoặc writer có bypass quyền, dữ liệu lỗi có thể tồn tại.

Các bài test:
- `$set` một field hợp lệ.
- `$unset` field required.
- `$set` sai type trong nested object.
- Thay phần của `price` và vô tình mất `currency`.
- Thao tác nhiều fields hợp lệ riêng lẻ nhưng tổ hợp sai.
- Concurrent PATCH lên cùng document.
- Update được match nhưng thực tế không modified.
- Không tìm thấy document.

**Một phép update hợp lệ về cú pháp vẫn có thể đưa state nghiệp vụ vào trạng thái sai** nếu validation chỉ ở request DTO chứ không kiểm state cuối.

## 23. Full replace là đường làm mất field phổ biến

Kịch bản:

~~~text
R1 đọc document cũ.
W2 cập nhật thành schema v2, thêm price.currency.
R1 giữ DTO cũ trong memory.
R1 replace document toàn bộ với dữ liệu DTO cũ.
~~~

Nếu không có version guard, document bị **schema downgrade** hoặc mất fields.

Một mô hình cập nhật an toàn hơn:

~~~javascript
db.products.updateOne(
  { _id: "p-101", revision: 5, schemaVersion: 2 },
  {
    $set: { name: "Bàn gỗ mới" },
    $inc: { revision: 1 }
  }
);
~~~

Đây là conditional update khái niệm. Caller phải kiểm `matchedCount`; nếu là 0, có thể là stale revision, schema mismatch hoặc không tồn tại. Không tự retry bằng cách bỏ điều kiện revision.

## 24. Upsert: nhánh insert và update có thể tạo hai schema khác nhau

Ví dụ:

~~~javascript
db.products.updateOne(
  { _id: "p-200" },
  {
    $set: { name: "Ghế nhỏ" },
    $setOnInsert: {
      schemaVersion: 2,
      lifecycle: "ACTIVE",
      price: { amountVnd: NumberLong("55000"), currency: "VND" },
      revision: NumberLong("0")
    }
  },
  { upsert: true }
);
~~~

Đây là ví dụ minh họa một upsert. Nếu document đã tồn tại theo v1, nhánh `$setOnInsert` không chạy; `$set` sẽ thêm `name` nhưng có thể vẫn giữ `title`/`priceVnd` và `schemaVersion` absent.

Do đó test phải có:
- Upsert khi key chưa có.
- Upsert khi đã có v1.
- Upsert khi đã có v2.
- Upsert khi đã có v3.
- Hai writers upsert cùng key đồng thời.
- Race với DELETE/TTL.
- Index uniqueness và retry outcomes.

**Một upsert dùng chung code path cho create/update không tự bảo đảm schema chuyển đổi đúng.**

## 25. CAS và revision chặn lost update, không thay schema validation

Giả sử:
~~~text
A đọc revision=4.
B đọc revision=4.
A đổi price, commit revision=5.
B đổi lifecycle dựa trên revision=4.
~~~

Nếu B ghi không điều kiện, có thể ghi đè thay đổi A. CAS:
~~~text
UPDATE only IF revision=4.
~~~

B nhận conflict và phải đọc lại state phù hợp schema rồi tính mutation mới.

Nhưng CAS **không kiểm kiểu giá, enum hay required fields**. Cần cả:
- Concurrency precondition.
- DB/application schema validation.
- Business invariant validation.
- Authorization.

## 26. Schema migration phải idempotent và có version guard

Backfill v1→v2:
~~~text
Read legacy Product.
Validate v1.
Transform to v2.
Apply only if source state/revision still matches.
Record progress.
~~~

Ví dụ pseudo:

~~~javascript
function toV2(old) {
  if (old.schemaVersion !== undefined) {
    throw new Error("EXPECTED_LEGACY_V1");
  }
  if (typeof old.title !== "string" || old.title.length === 0) {
    throw new Error("INVALID_LEGACY_TITLE");
  }
  if (!Number.isSafeInteger(old.priceVnd) || old.priceVnd < 0) {
    throw new Error("INVALID_LEGACY_PRICE");
  }
  return {
    schemaVersion: 2,
    name: old.title,
    price: { amountVnd: old.priceVnd, currency: "VND" },
    lifecycle: old.active ? "ACTIVE" : "PAUSED"
  };
}
~~~

Đoạn JavaScript trên để diễn giải logic transform; với dữ liệu BSON Int64 vượt safe-integer của JavaScript cần xử lý kiểu riêng, không ép kiểu bừa.

## 27. Backfill phải kiểm source revision lúc commit

Timeline:
~~~text
T0: Migrator đọc v1, revision=4.
T1: API sửa tên, revision=5.
T2: Migrator ghi v2 từ snapshot revision=4.
~~~

Nếu T2 overwrite không điều kiện, tên mới bị mất.

Một khung MongoDB:

~~~javascript
const patch = toV2(legacy);
const result = db.products.updateOne(
  {
    _id: legacy._id,
    schemaVersion: { $exists: false },
    revision: legacy.revision
  },
  {
    $set: patch,
    $unset: { title: "", priceVnd: "", active: "" },
    $inc: { revision: 1 }
  }
);

if (result.matchedCount === 0) {
  // Một writer khác đã đổi state hoặc schema; đọc lại và quyết định.
}
~~~

Một update document có thể áp dụng các thay đổi fields cùng lúc trong phạm vi atomicity của MongoDB document, nhưng business semantics của record cần được kiểm sau chuyển đổi. Nếu cần transaction trên nhiều documents, phải dùng hỗ trợ/thiết kế tương ứng.

## 28. Quét backfill khi source vẫn ghi

Không nên dựa vào offset pagination đơn giản trên dataset đang biến động:

~~~text
Page 1: skip 0 limit 1000.
Concurrent insert/delete.
Page 2: skip 1000 limit 1000.
~~~

Phần tử có thể bị bỏ sót hoặc trùng.

Ưu tiên:
- Snapshot cursor/consistent read theo capability.
- Range scan theo stable key.
- Checkpoint per shard/partition.
- Đếm coverage và reconciliation.
- Bounded concurrency/QPS.
- CDC/outbox để bắt writes phát sinh.
- Retry idempotent theo schema/revision.
- Quarantine records không transform được.

Một bản scan hoàn tất không chứng minh không còn legacy records nếu các writers cũ tiếp tục tạo thêm.

## 29. Source of truth trong giai đoạn cùng tồn tại

Chọn rõ:
~~~text
Production MongoDB: nguồn authoritative.
Migration worker: chỉ biến đổi các document hợp lệ và có version guard.
Search/Redis: read models hoặc cache, không quyết định schema nguồn.
CDC: chuyển những thay đổi đã commit đến downstream.
~~~

Nếu hai applications cùng ghi hai schema vào cùng collection, phải có policy ràng buộc:
- Writer nào được phép tạo v1/v2/v3.
- Có cấm downgrade schema không.
- Ai cập nhật revision.
- Các background writes có đi qua validation không.
- Đường direct DB/admin writes có quyền nào.

Không để schema version được client tùy ý chọn chỉ vì request có field `schemaVersion`.

## 30. CDC events và replay cũng có phiên bản

Một event cũ:

~~~json
{
  "eventType": "ProductUpdated",
  "eventSchemaVersion": 1,
  "productId": "p-101",
  "priceVnd": 125000
}
~~~

Event mới:

~~~json
{
  "eventType": "ProductUpdated",
  "eventSchemaVersion": 2,
  "productId": "p-101",
  "price": {"amountVnd":125000,"currency":"VND"}
}
~~~

Nếu consumer chỉ xử lý v2, replay queue từ tháng trước có thể fail. Cần test:
- Consumer v2 đọc event v1/v2.
- Event v1 replay không ghi đè document v2 có revision mới.
- Duplicates/retries không tạo effect lặp.
- DELETE/tombstone được hiểu đúng.
- Full-document after-image hay patch có đủ thông tin transform không.
- Checkpoint lưu sau target apply bền.

**Dữ liệu ở database và dữ liệu trong event history có thể có vòng đời phiên bản khác nhau.**

## 31. Đừng đánh đồng event version và source document version

Một document `schemaVersion=3` vẫn có thể phát event envelope `eventSchemaVersion=1` nếu event contract chưa đổi. Ngược lại, một event v2 có thể mô tả mutation trên document v1 do migration transition.

Hãy đặt tên và nghĩa rõ:
~~~text
eventSchemaVersion
documentSchemaVersion
sourceRevision
operationId
eventId
~~~

Nếu consumer so `eventSchemaVersion` để quyết định update mới hơn/đến sau, đó là một lỗi ordering nghiêm trọng. Ordering phải dựa vào **source revision, event position hoặc giao thức có bảo đảm tương ứng**, không dựa vào cấu trúc serialization.

## 32. DELETE, TTL và tombstone khi migrate

Một key v1 được đọc để backfill, sau đó bị xóa:
~~~text
T0 backfill đọc document v1.
T1 source DELETE document.
T2 CDC áp dụng DELETE.
T3 backfill ghi lại v2 từ snapshot cũ.
~~~

Nếu không có tombstone/version gate, record bị hồi sinh.

Test:
- DELETE trước backfill.
- DELETE sau snapshot read nhưng trước target write.
- DELETE event đến trước/ sau upsert.
- TTL expiry và explicit DELETE có semantics khác nhau.
- Soft delete giữ status/retention.
- Resnapshot sau CDC cursor expiry.

Ở document version history, cần xác định **xóa nào thuộc business state và xóa nào chỉ là dọn dữ liệu vật lý**.

## 33. Schema validation không tự kiểm uniqueness

Hai products:
~~~json
{"_id":"p-1","tenantId":"t-1","externalSku":"sku-9"}
{"_id":"p-2","tenantId":"t-1","externalSku":"sku-9"}
~~~

Mỗi document có thể hợp lệ theo JSON Schema, nhưng nghiệp vụ yêu cầu unique `(tenantId, externalSku)`.

Cần:
- Unique index/conditional write nếu engine hỗ trợ trong phạm vi cần.
- Kiểm các sharding caveats của uniqueness.
- Test concurrent creates.
- Test upsert conflict.
- Test dữ liệu legacy duplicates trước khi dựng index.
- Test partial/sparse index semantics nếu dùng.

**Document validity và cross-document uniqueness là hai hợp đồng khác nhau.**

## 34. Validation không tự thực thi tenant isolation

Một document có đủ fields nhưng sai tenant:

~~~json
{
  "_id":"p-101",
  "tenantId":"tenant-B",
  "schemaVersion":2,
  "name":"Bàn gỗ",
  "price":{"amountVnd":125000,"currency":"VND"},
  "lifecycle":"ACTIVE"
}
~~~

Nó có thể hợp lệ về schema nhưng không được phép tạo bởi principal thuộc tenant A.

Test cần:
- Filter tenant theo verified auth context.
- Chặn update thay tenantId.
- Không tin tenantId do client tự khai.
- Read/write authorization tests cho từng version.
- Backfill không gộp cross-tenant keys.
- Raw error messages không lộ dữ liệu tenant khác.
- Schema validation bật ở storage không thay service authorization.

## 35. “Strict reader” và “tolerant reader” đều có chỗ dùng

**Strict reader**: reject dữ liệu không đúng contract, hữu ích ở đường quyết định tài chính/quyền.

**Tolerant reader**: chấp nhận fields chưa biết hoặc các version được công bố, hữu ích cho rolling upgrades và event consumers.

Tuy nhiên **tolerance phải có giới hạn**:
- Unknown optional field: có thể bỏ qua khi đọc.
- Unknown lifecycle enum: có thể yêu cầu fail an toàn.
- Missing required price: không được mặc định bằng 0.
- Version unsupported: lỗi rõ, không thử đoán.
- Type mismatch: quarantine/alert, tránh ép kiểu im lặng.

Lựa chọn phải dựa trên hậu quả nghiệp vụ, không dùng một cờ “ignoreUnknown=true” cho mọi trường hợp.

## 36. Java: adapter đọc nhiều schema versions

Ví dụ minh họa, không phải mã đầy đủ của một framework:

~~~java
record PriceView(long amountVnd, String currency) {}

PriceView parsePrice(Document doc) {
    Object version = doc.get("schemaVersion");

    if (version == null && !doc.containsKey("schemaVersion")) {
        // Legacy v1: kiểm tra đúng kiểu, không ép sang 0 nếu thiếu.
        Object value = doc.get("priceVnd");
        if (!(value instanceof Number number)) {
            throw new InvalidStoredProductException("INVALID_V1_PRICE");
        }
        return new PriceView(number.longValue(), "VND");
    }

    if (Integer.valueOf(2).equals(version)
            || Integer.valueOf(3).equals(version)) {
        Document price = doc.get("price", Document.class);
        if (price == null || !price.containsKey("amountVnd")) {
            throw new InvalidStoredProductException("INVALID_PRICE");
        }
        Object amount = price.get("amountVnd");
        if (!(amount instanceof Number number)) {
            throw new InvalidStoredProductException("INVALID_PRICE_TYPE");
        }
        String currency = price.getString("currency");
        return new PriceView(number.longValue(), currency);
    }

    throw new UnsupportedSchemaVersionException(String.valueOf(version));
}
~~~

Đây là **ví dụ ý tưởng routing version**, chưa gồm kiểm numeric precision/range, enum/currency, null safety đầy đủ và schema business rules. Các bài test phải chứng minh những checks này; không coi `Number.longValue()` tự xử lý mọi loại BSON an toàn.

## 37. Java: không xử lý sai bằng default âm thầm

Một antipattern:

~~~java
long price = Optional.ofNullable(document.getLong("priceVnd"))
        .orElse(0L);
~~~

Nếu document v2 không có `priceVnd`, giá bị biến thành 0 mà không có exception. Đây là **silent data corruption ở read path**, dù database thực tế lưu đúng.

Tốt hơn:
- Parse theo `schemaVersion`.
- Khi field required thiếu, trả typed error.
- Ghi metric lỗi theo version và operation.
- Không log raw PII/document.
- Có quarantine/backfill workflow.
- Không phát giá trị giả ra checkout/payment.

Với dữ liệu không critical, có thể dùng fallback đã được định nghĩa, nhưng phải test rằng fallback không vi phạm invariant.

## 38. Java: contract tests giữa writer và reader

Một ý tưởng test:

~~~java
@Test
void readerV2CanReadLegacyV1() {
    Document legacy = fixture("product-v1.json");
    ProductView result = readerV2.read(legacy);
    assertEquals("Bàn gỗ", result.name());
    assertEquals(125000L, result.priceVnd());
}

@Test
void readerRejectsUnknownVersion() {
    Document future = new Document("schemaVersion", 99);
    assertThrows(UnsupportedSchemaVersionException.class,
        () -> readerV2.read(future));
}
~~~

Fixture `product-v1.json` trong ví dụ là một tên minh họa, không yêu cầu tạo file ngoài Markdown bài học.

Các tests cần:
- Writer W2 sinh document hợp lệ theo DB validator.
- R2 đọc được mọi fixtures v1/v2.
- W2 không làm mất optional metadata của record khi PATCH.
- R1 không bị route sang dữ liệu v2 khi chưa compatible.
- R3 xử lý v1/v2/v3 theo policy.
- Unsupported/corrupt versions báo lỗi có kiểm soát.

## 39. Golden fixtures cần đa dạng, không chỉ một bản đẹp

Một bộ fixtures hợp lý:
~~~text
v1-minimal-valid
v1-with-extra-legacy-fields
v1-missing-price
v1-price-as-string
v1-empty-title
v2-minimal-valid
v2-full-valid
v2-null-name
v2-missing-currency
v2-unknown-lifecycle
v2-negative-price
v2-extra-fields
v3-valid-tags
v3-tags-wrong-type
v3-empty-tags
unknown-version
version-null
mixed-v1-v2-fields
~~~

Mỗi fixture cần expected outcome:
- Valid stored state?
- Reader nào đọc được?
- Writer nào được phép sửa?
- Migration transform ra sao?
- HTTP error hoặc quarantine code nào?
- Có mất thông tin nghiệp vụ không?

**Negative fixtures quan trọng như positive fixtures**, vì validation chủ yếu có giá trị khi nó chặn dữ liệu sai.

## 40. Bảng test bắt buộc theo thao tác

| Thao tác | Dữ liệu v1 | Dữ liệu v2 | Dữ liệu v3 | Input lỗi |
|---|---|---|---|---|
| INSERT | Theo policy còn cho legacy writer? | Phải hợp lệ | Chỉ khi v3 enabled | Bị từ chối |
| FIND/read | Adapter phù hợp | Đúng giá trị | Chỉ reader hỗ trợ | Error rõ |
| UPDATE `$set` | Không tạo hybrid sai | Giữ full invariant | Giữ future fields | Bị từ chối |
| UPDATE `$unset` | Required legacy fields | Required new fields | Required new fields | Bị từ chối |
| REPLACE | Chống downgrade | Không mất metadata | Không mất tags | Bị từ chối |
| UPSERT missing | Tạo schema được chỉ định | Tạo schema được chỉ định | Theo feature flag | Không sinh half-valid |
| UPSERT existing | Không chèn nửa v2 | Không phá v2 | Không phá v3 | Conflict rõ |
| DELETE/TTL | Không hồi sinh | Không hồi sinh | Không hồi sinh | Policy đúng |
| MIGRATE | v1→v2 idempotent | No-op/skip | Không downgrade | Quarantine |
| CDC REPLAY | Có event adapter | Idempotent | Version-aware | Dead letter/alert |

Đây là test-plan matrix; từng dự án cần triển khai những đường write thực và quyền truy cập khác nhau. Đặc biệt full replace có thể bị cấm hoàn toàn để giảm rủi ro.

## 41. Kiểm thử transaction boundaries và lỗi giữa chừng

Một nghiệp vụ:
~~~text
Update product schema.
Update inventory projection.
Publish ProductChanged event.
~~~

Nếu ba bước không atomic:
- Product đã v2, projection còn v1.
- Event được gửi nhưng DB rollback.
- DB commit xong, publisher crash trước khi gửi.
- Consumer nhận event hai lần.

Test:
- Crash sau từng bước.
- Network timeout/unknown commit.
- Retry cùng operationId.
- Outbox atomic nếu được hỗ trợ.
- Event dedup.
- Reconciliation path.
- Business API không dùng projection chưa bắt kịp cho hard invariant.

Document schema validation **không bảo đảm một workflow gồm nhiều records/systems có tính nguyên tử**.

## 42. Property-based testing cho version adapters

Thay vì chỉ fixtures cố định, sinh nhiều document hợp lệ:
- Tên Unicode dài/ngắn.
- Giá 0/max.
- Tags mảng rỗng/đầy.
- Nested metadata khác nhau.
- Các enum hợp lệ.
- V1 có/không field tùy chọn.
- Tổ hợp số revision và version.

Kiểm các thuộc tính:

\[
\operatorname{parseV2}(\operatorname{encodeV2}(x))=x
\]

trong phạm vi mô hình business `x`, và:

\[
\operatorname{canonical}(\operatorname{migrateV1toV2}(d))
=\operatorname{canonical}(d)
\]

nếu `canonical` bỏ qua khác biệt biểu diễn có chủ đích.

Không so JSON bytes nếu schema mới đổi field names/order; phải so **ngữ nghĩa**.

## 43. Metamorphic testing khi không có oracle đơn giản

Một số invariant:
- Thêm optional field không làm đổi business price.
- Đổi thứ tự fields JSON không làm đổi kết quả.
- Replay cùng migration hai lần không làm đổi business state lần hai.
- Sắp xếp tags nếu business coi set thì normalized result phải tương đương.
- Chuyển `active=true` v1 sang `lifecycle=ACTIVE` v2 không đổi eligibility.
- Đổi timezone representation của cùng instant không đổi timestamp nghiệp vụ.
- Thay writer version theo policy không làm giảm revision.

Các kiểm tra này tìm lỗi khó thấy hơn so với chỉ assert “không throw”.

## 44. Fuzzing dữ liệu lỗi một cách an toàn

Có thể tạo biến thể:
- Xóa một field required.
- Thay type string thành object/array.
- Đổi enum thành chuỗi chưa biết.
- Lồng object 100 cấp nếu hệ có giới hạn.
- Mảng cực lớn.
- Chuỗi Unicode malformed/normalized khác.
- Numeric overflow.
- Field name gần giống do typo.
- Duplicate logical IDs.
- SchemaVersion kiểu chuỗi thay số.

Mục tiêu:
- Parser không crash uncontrolled.
- Database chặn invalid writes theo contract.
- API không trả thành công giả.
- Không tạo memory/CPU denial of service.
- Logs không leak raw sensitive fixture.

Chạy fuzz ở môi trường cô lập và giới hạn tài nguyên; không đẩy payload phá tải vào production.

## 45. Kiểm thử thực tế theo engine: MongoDB

Một môi trường integration test đáng tin nên sử dụng database thực ở version tương ứng (có thể qua container/test environment được phép), không chỉ mock collection.

Những tests nên có:
1. Tạo collection với validator.
2. Insert v1/v2 hợp lệ theo giai đoạn.
3. Insert invalid type/enum/missing fields.
4. Update/replace/upsert theo từng nhánh.
5. Đổi `validationAction`/`validationLevel` ở môi trường thử và kiểm persisted outcome.
6. Test unique index song song validator.
7. Test quyền `bypassDocumentValidation`.
8. Test concurrent revision conflicts.
9. Test migration + Change Streams/CDC nếu luồng triển khai dùng.
10. Test index/schema metadata sau backup/restore.

Một mock Java repository thường không thực thi đúng `$jsonSchema`, BSON type, atomic update hay index uniqueness như server thật.

## 46. Cassandra: schema evolution và schema agreement

Cassandra là wide-column với table schema cụ thể; thay column type, partition/clustering key hay table layout không giống thêm JSON field trong document.

Cần test:
- `ALTER TABLE` theo khả năng thực của version.
- Schema agreement giữa nodes trước khi triển khai query mới.
- Các client drivers/serializers cũ và mới.
- Column mới chưa có ở rows cũ (null/missing representation theo API).
- UDT/type changes khi có.
- Replication strategy, TTL, tombstones và consistency.
- Backfill những table mới/denormalized views.
- Dữ liệu ở nhiều partitions nếu workflow yêu cầu invariant.
- Không tự chuyển đổi partition key đang live chỉ bằng `ALTER`.

Với một mô hình mới theo query, đôi khi phương án an toàn là **tạo table mới, backfill và chuyển reads/writes theo từng phase** hơn là sửa table cũ in place.

## 47. DynamoDB: key/index schema và app-side validation

DynamoDB kiểm soát một số yêu cầu của key schema, index keys và item types; nhưng không ép mọi item phải có cùng toàn bộ attributes nghiệp vụ.

Ví dụ v1 có:
~~~json
{"pk":"PRODUCT#101","priceVnd":125000}
~~~

v2 có:
~~~json
{
  "pk":"PRODUCT#101",
  "schemaVersion":2,
  "price":{"amountVnd":125000,"currency":"VND"}
}
~~~

Cần test:
- Key types và constraints.
- App validators với attributes missing/null.
- ConditionExpression ngăn stale version overwrite.
- Transactional writes nếu nhiều items cần invariant.
- GSI keys và eventual update propagation.
- Streams image format cho v1/v2.
- TTL attribute/expiration semantics.
- IAM permissions và tenant access.
- Backfill Scan/Query dưới writes đồng thời.

Một GSI tồn tại không chứng minh mọi old items có đủ attributes để xuất hiện trong index đó; cần test sparse/missing attribute behavior theo index definition.

## 48. Redis: schema do application/serialization nắm giữ

Redis có thể giữ strings/hashes/lists/JSON qua module hoặc quy ước ứng dụng. Nhưng tên key giống nhau không đảm bảo values có cùng định dạng.

Ví dụ:
~~~text
product:101 -> v1 JSON: {"title":"Bàn gỗ","priceVnd":125000}
product:102 -> v2 JSON: {"schemaVersion":2,"name":"Bàn gỗ",...}
~~~

Test:
- Codec giải mã được v1/v2.
- Không ghi đè bằng serialization cũ.
- TTL không bị reset vô ý trong migration.
- Lua/transaction/script có assumptions về hash fields không.
- Cache invalidation key namespace.
- Race giữa cache fill cũ và write mới.
- Redis Cluster keys/hash slots nếu multi-key operation.
- ACL không cho producer cũ ghi schema deprecated.

Nếu Redis chỉ là cache, có thể flush/rebuild **trong một kế hoạch an toàn**, nhưng phải kiểm nguồn có đủ capacity và tránh cache stampede. Nếu Redis chứa authoritative data, cần phương án kiểm đúng mạnh hơn.

## 49. CouchDB: validate_doc_update, revisions và conflicts

Trong những cách triển khai có hỗ trợ validation trong design documents (ví dụ `validate_doc_update` theo semantics CouchDB/version), cần phân biệt:
- Validation của document mới/cập nhật.
- `oldDoc` và `newDoc` khi validator được gọi.
- User/security context.
- Revision conflicts.
- `_changes` feed và replicated revisions.
- Design document version rollout.
- Deletion/purge behavior.
- Dữ liệu đã tồn tại trước khi rule mới được thêm.

Không giả định validator ứng dụng nhìn một update order tuyệt đối trên mọi replicas nếu hệ cho phép concurrent revisions. Test cả conflicting revisions và cách chọn/merge phiên bản theo business contract.

## 50. Managed service và schema registry không thay integration tests

Một schema registry/event contract có thể giúp kiểm Avro/JSON/Protobuf compatibility, nhưng:
- Database item/document vẫn có thể khác event envelope.
- Một event hợp lệ vẫn có thể tạo state DB không hợp lệ.
- Compatibility checker có thể kiểm syntax/schema chứ không hiểu semantic conversion.
- Readers có thể chứa defaults nguy hiểm.
- Partial updates/TTL/transactions ở sink có thể làm sai.

Kết hợp **contract tests + DB integration tests + end-to-end migration tests**, không chọn chỉ một.

## 51. Testing trên backup/restore và dữ liệu lịch sử

Một restore về recovery point cũ có thể tạo lại:
- Legacy v1 documents.
- Event records với event schema v1.
- Index/validator definitions phiên bản cũ.
- Permission/role configurations khác.
- Background jobs không tương thích.

Cần test sau restore:
1. Reader hiện tại có thể đọc recovery data cũ không?
2. Migration scripts còn tái chạy được không?
3. Backfill được resume an toàn không?
4. Validator nào áp dụng cho recovery state?
5. Current writer có thể tạo dữ liệu hợp lệ không?
6. CDC checkpoint có tương thích recovery point không?
7. Business invariants và tenant authorization có được giữ không?

**Sunset hỗ trợ v1 ở production hiện tại chưa chắc được phép xóa decoder v1 khỏi mọi công cụ phục hồi.**

## 52. Canary và shadow-read trong rollout

Trong giai đoạn trước khi đổi writer:
- Mỗi request thật vẫn được phục vụ từ reader đang ổn định.
- Shadow-read với adapter mới trên cùng document/version.
- So normalized business output: tên, giá, lifecycle.
- Không chạy writes/side effects từ shadow code.
- Ghi mismatch theo schemaVersion/errorCode, không log raw document nhạy.
- Đếm records version cũ/mới theo phạm vi.
- Chỉ mở writer v2 sau khi reader coverage và error budget đạt.

Shadow-read cần kiểm concurrency: hai reads ở hai thời điểm khác nhau có thể thấy revisions khác nhau, tạo **mismatch giả**. Nên so cùng source revision hoặc dùng snapshot/controlled fixtures khi cần.

## 53. Chỉ số quan sát phiên bản dữ liệu

| Metric | Điều cần biết |
|---|---|
| `documents_by_schema_version` | Còn bao nhiêu v1/v2/v3? |
| `reads_by_version` | Readers thực sự gặp version nào? |
| `decode_failures_by_version` | Có type mismatch sau deploy? |
| `validation_rejections` | Database đang chặn gì? |
| `validation_warnings` | Có invalid writes vẫn được cho qua? |
| `legacy_writer_attempts` | Có producer cũ còn hoạt động? |
| `schema_downgrade_attempts` | Có writer làm version tụt? |
| `backfill_processed/skipped/failed` | Tiến độ chuyển đổi |
| `backfill_revision_conflicts` | Có updates đồng thời? |
| `cdc_apply_failures` | Incremental sync có bỏ sót? |
| `unknown_version_count` | Có schema ngoài contract? |
| `shadow_read_mismatches` | Adapter mới trả khác kết quả? |
| `quarantine_oldest_age` | Dữ liệu lỗi bị kẹt bao lâu? |
| `constraint_violations` | Uniqueness/business invariants |
| `schema_config_drift` | Validator thực có khác bản được duyệt? |

Không đặt `_id`, email hoặc tenant ID tùy ý vào metric labels nếu cardinality/PII không được kiểm soát.

## 54. Khi nào được chặn ghi v1?

Điều kiện quyết định contract phase:
- All W1 application instances đã được thay thế hoặc bị write-fenced.
- Direct DB writers, imports, cron jobs đã nâng cấp.
- CDC consumers và replay queues không còn phát v1 theo đường gây downgrade.
- Remaining legacy documents đã được backfill và reconcile.
- Validator v2-only đã được thử với dữ liệu/requests thực tế.
- Các read paths được đo không còn cần v1 trong production scope.
- Backup/DR vẫn có decoder/migration tool cho recovery point cũ.
- Có rollback/rollforward plan và owner.

Cần chuyển “validator accept v1+v2” sang “v2-only” như một **thay đổi sản phẩm có rủi ro**, không chỉ sửa một config không cần thử nghiệm.

## 55. Runbook: new reader đọc giá bằng 0

1. Xác định affected product/version và input source một cách an toàn.
2. Kiểm có dùng `getLong("priceVnd")` trên document v2 không.
3. Xem parser có default missing price thành zero không.
4. Phân tích BSON type và currency/units.
5. Chặn các quyết định giá nguy hiểm bằng fail-safe behavior.
6. Sửa adapter theo schemaVersion.
7. Thêm fixtures v1/v2/null/missing/string-price.
8. Kiểm response end-to-end và domain invariant.
9. Theo dõi decode failures và rollout canary.
10. Không tự sửa hàng loạt dữ liệu đúng chỉ vì parser sai.

## 56. Runbook: validator từ chối writes sau rollout

1. Kiểm validator version/config ở database thực.
2. Kiểm writer release và schemaVersion được phát.
3. Kiểm BSON type, required/enum/nested fields.
4. Kiểm `validationLevel`, `validationAction`.
5. Kiểm upsert insert branch vs update branch.
6. Kiểm stale old writers và direct jobs.
7. Phân tích sample sanitized failure codes.
8. Nếu lỗi do config, rollback/rollforward qua change control.
9. Không mở bypass toàn cụm để “chữa cháy” vô thời hạn.
10. Thêm integration test cho đường thao tác gây lỗi.

## 57. Runbook: backfill v1→v2 bị xung đột

1. Kiểm `matchedCount=0` do revision hoặc schema mismatch.
2. Đọc lại record với consistency phù hợp.
3. Nếu document đã v2/v3, không downgrade.
4. Nếu v1 đã đổi revision, transform phiên bản mới hơn.
5. Nếu invalid legacy, quarantine có owner.
6. Retry có giới hạn, idempotency.
7. Giới hạn batch/QPS để không ảnh hưởng SLO.
8. Kiểm DELETE/tombstone/TTL.
9. Reconcile state/count/version distribution.
10. Ghi tiến độ per range và stop nếu conflict rate bất thường.

## 58. Runbook: dữ liệu v3 lọt vào app v1

1. Kiểm writer nào đã phát v3 và feature flag.
2. Kiểm deployment order/read routing.
3. Kiểm old app deserialize/replace semantics.
4. Dừng những writers gây downgrade, dùng fencing/ACL nếu cần.
5. Xác minh records đã mất fields/version chưa.
6. Reconcile nguồn dữ liệu và audit/change feed.
7. Sửa reader/writer compatibility trước khi mở traffic.
8. Không map enum mới sang trạng thái nguy hiểm.
9. Thêm deployment matrix test/canary.
10. Đưa incident vào plan contract phase.

## 59. Những nhầm lẫn thường gặp

| Hiểu nhầm | Vì sao sai | Điều đúng |
|---|---|---|
| NoSQL không có schema | Schema vẫn tồn tại ở dữ liệu/ứng dụng | Xác định contract |
| Một validator là đủ | Nhiều writers và business rules khác | Multi-layer tests |
| Schema hợp lệ thì reader đúng | Reader có thể default sai | Contract tests |
| `schemaVersion` là revision | Mục đích khác | Tách schema vs mutation |
| Missing và null giống nhau | Semantics khác | Test riêng |
| String số và Int64 như nhau | Precision/codec khác | Typed validation |
| Field lạ bỏ qua nghĩa compatible | Full replace có thể xóa field | Read/write matrix |
| Enum mới không hại app cũ | Old switch/default có thể sai | Test old reader |
| Tạo index là kiểm schema | Index chỉ cover constraints riêng | Validator + index |
| Validator chặn cross-tenant access | Không hiểu auth context đầy đủ | Authorization tests |
| `moderate` luôn kiểm mọi update | Có behavior riêng với invalid legacy | Test mode |
| `warn` từ chối ghi sai | Thường chỉ cảnh báo | Kiểm persisted outcome |
| Mọi import đều qua validator | Có quyền bypass hoặc tool behavior | Security/integration |
| PATCH một field luôn an toàn | State cuối có thể invalid | Full-document invariant |
| Upsert insert = update | `$setOnInsert` không chạy khi đã có | Test hai nhánh |
| CAS ngăn schema lỗi | CAS chỉ xử lý concurrency | Kết hợp validation |
| Read tolerant = write tolerant | Writer có thể downgrade | Preserve fields/guard |
| Bật writer v2 trước reader | Old app có thể fail | Expand readers first |
| Có một fixture happy path là đủ | Thiếu null/invalid/version lạ | Negative fixtures |
| Migration chỉ cần chuyển count | Giá/enum/TTL có thể sai | Semantic reconciliation |
| Backfill quét xong là hết v1 | Old writers vẫn tạo v1 | Writer inventory/fencing |
| CDC event replay một lần | At-least-once/retry | Idempotency |
| Event schemaVersion là commit order | Không có nghĩa đó | Source revision/position |
| DELETE không cần test | Có thể hồi sinh | Tombstone/version |
| Redis có JSON nên có schema DB | Thường application-managed | Codec/TTL tests |
| Cassandra như document DB | Wide-column schema và partition key | Engine-specific |
| DynamoDB kiểm mọi attribute | Nhiều attributes application-defined | Application validators |
| Mock DB thay integration test | Không mô phỏng BSON/index/atomicity | Real-engine tests |
| Restore backup mới là đủ | Backups cũ có legacy schema | DR contract |
| Reader mới không throw là đúng | Có thể default giá 0 | Verify business values |
| `schemaVersion` từ client tin được | Client có thể chọn version lạ | Server-controlled writers |

## 60. Bài tập thực hành

### Bài tập 1 — Ba lớp schema

Liệt kê database validator, application/domain validator và serialization contract của một NoSQL Product. Cho ví dụ lỗi mà từng lớp không tự chặn được.

### Bài tập 2 — Ba phiên bản cùng tồn tại

Với Product v1 `title/priceVnd`, v2 `name/price`, v3 thêm `tags`, thiết kế readers/writers compatibility matrix và tiêu chí an toàn của từng ô.

### Bài tập 3 — SchemaVersion và revision

Một document đang ở `schemaVersion=2, revision=19`; update giá làm revision 20. Giải thích vì sao schemaVersion không đổi và trường nào dùng cho CAS.

### Bài tập 4 — Legacy unversioned

Một số document cũ thiếu schemaVersion; một số document mới bị lỗi schemaVersion=null. Thiết kế parser không đồng nhất hai trường hợp.

### Bài tập 5 — MongoDB validator v2

Viết `$jsonSchema` bắt buộc name, price.amountVnd, price.currency và lifecycle; chặn giá âm, loại tiền không hợp lệ và kiểu sai.

### Bài tập 6 — Validator mixed schema

Viết logic `$or` chấp nhận legacy v1 không có schemaVersion và v2 explicit, đồng thời reject document hybrid thiếu fields bắt buộc.

### Bài tập 7 — Strict vs moderate

Tạo một document legacy vốn invalid, thử insert/update với các mức validationLevel ở môi trường test. Đo kết quả write và explain policy sử dụng.

### Bài tập 8 — Warn vs error

Một team bật validationAction=warn nhưng nghĩ tất cả invalid writes bị chặn. Thiết kế integration tests chứng minh persisted outcome.

### Bài tập 9 — Bypass privilege

Một migration principal có quyền bypassDocumentValidation. Thiết kế giới hạn quyền, audit, kiểm lại dữ liệu và thu hồi sau migration.

### Bài tập 10 — Missing/null/type

Với field name, liệt kê test cho missing, null, empty string, integer, valid Unicode. Quy định expected outcome trong DB và Java reader.

### Bài tập 11 — Numeric precision

Một data import ghi giá lớn dưới dạng Double, một writer khác ghi Int64. Thiết kế test phát hiện precision loss và chuẩn kiểu.

### Bài tập 12 — Enum mới

W3 thêm lifecycle=DISCONTINUED, R2 chỉ hiểu ACTIVE/PAUSED/ARCHIVED. Thiết kế rollout không trả trạng thái ACTIVE giả.

### Bài tập 13 — Unknown field và replace

Old reader bỏ qua metadata mới rồi full-replace. Chứng minh lost field và đề xuất PATCH/conditional update.

### Bài tập 14 — Nested array

V3 thêm tags. Tạo positive/negative fixtures: missing, null, [], duplicates, wrong type, long tags và normalization.

### Bài tập 15 — Partial update

Một PATCH `$unset:{name:""}`. Kỳ vọng DB validator và business API như thế nào? Kiểm full state sau update.

### Bài tập 16 — Upsert existing v1

Một upsert có `$setOnInsert` cho schemaVersion=2 nhưng match v1 đã tồn tại. Vì sao tạo hybrid, và cách xử lý?

### Bài tập 17 — Lost update

Hai Java instances đọc revision 4 và cùng cập nhật. Thiết kế conditional update, conflict handling và retry đúng.

### Bài tập 18 — Backfill CAS

Migrator đọc v1 revision 4, API cập nhật revision 5 trước khi migrator ghi. Viết filter/guard để không mất thay đổi.

### Bài tập 19 — Idempotent migration

Chạy chuyển v1→v2 hai lần. Kết quả hợp lệ cần như thế nào? Nêu conditions để lần hai skip không tăng revision không cần thiết.

### Bài tập 20 — Source writers inventory

Một batch job vẫn tạo v1 khi team nghĩ backfill xong. Thiết kế metrics/permissions để phát hiện và ngăn legacy writes.

### Bài tập 21 — CDC replay

Consumer v2 phải đọc event schema v1/v2. Thiết kế event adapters và source revision guard để không thụt lùi state.

### Bài tập 22 — Tombstone/TTL

Backfill đọc record, sau đó source DELETE; CDC delete tới target trước snapshot upsert. Thiết kế chống hồi sinh.

### Bài tập 23 — Uniqueness

Hai products cùng tenant/externalSku nhưng khác `_id`. Vì sao JSON Schema không đủ? Chọn unique index và test concurrent insert.

### Bài tập 24 — Tenant isolation

Document hợp lệ về schema nhưng chứa tenantId của người khác. Thiết kế API/security tests trong quá trình migration.

### Bài tập 25 — Property-based testing

Viết ba tính chất cho encode/decode v2, transform v1→v2 và normalize business state. Sinh dữ liệu biên.

### Bài tập 26 — Fuzzing

Tạo 12 biến thể input lỗi theo missing, null, BSON type, nested array, numeric overflow và unknown fields; mô tả expected failure mode.

### Bài tập 27 — Integration test MongoDB

Một mock repository pass tất cả tests nhưng production không cho insert v2. Thiết kế test dùng DB engine thật, validator, unique index và BSON types.

### Bài tập 28 — Cassandra schema agreement

Rolling upgrade thêm column mới trong Cassandra khi clients cũ còn chạy. Thiết kế test schema agreement, nulls, driver compatibility và backfill.

### Bài tập 29 — DynamoDB GSI

GSI mới chỉ index items có attribute mới, trong khi legacy items thiếu. Thiết kế kiểm tra coverage và migration.

### Bài tập 30 — Redis serialization

Redis chứa v1/v2 JSON cùng key prefix. Thiết kế codec tests, TTL preservation và chặn old writers ghi đè v2.

### Bài tập 31 — CouchDB revisions

Một validator mới được deploy khi document cũ và conflict revisions còn tồn tại. Thiết kế test update/replication/conflict semantics theo deployment.

### Bài tập 32 — Backup/restore

Recovery snapshot chứa schema v1 nhưng current app chỉ đọc v3. Thiết kế restore drill và migration/decoder compatibility.

### Bài tập 33 — Observability

Thiết kế dashboard theo schemaVersion, read/decode failures, validator rejections/warnings, stale writer attempts, backfill conflicts và unknown versions; hạn chế metric label cardinality.

### Bài tập 34 — Triển khai rolling

Tạo timeline expand readers → mở validator mixed → bật writer v2 → backfill → verify → chặn writer v1 → contract validator. Nêu GO/NO-GO cho từng phase.

### Bài tập 35 — Kiểm thử tổng hợp

Một nền tảng dùng Java API, MongoDB catalog, DynamoDB preferences, Redis cache và Cassandra events; còn một số batch jobs cũ. Hãy thiết kế:

1. Data/schema versions và policy tương thích.
2. Positive/negative fixtures theo engine.
3. DB validators, domain validators, serializer adapters.
4. CRUD/UPSERT/PATCH/REPLACE/DELETE tests.
5. CAS, concurrency và stale writer protection.
6. Backfill, CDC, version guards và tombstones.
7. Index uniqueness và tenant authorization.
8. Shadow-read, rollout gates và metrics.
9. Backup/restore compatibility với legacy records.
10. Điều kiện loại bỏ v1 và rollback/rollforward.

### Bài tập 36 — Phê bình kế hoạch thiếu an toàn

Một đội đề xuất:

~~~text
NoSQL không có schema, không cần validator.
Chỉ test INSERT một document v2 đẹp.
Reader mới nếu thiếu price thì trả 0.
Đổi writer sang v2 trước khi nâng các readers cũ.
Bật validationAction=warn rồi coi invalid writes bị chặn.
Backfill replaceOne không cần revision guard.
Old batch job vẫn tạo v1 cũng không sao.
Gộp schemaVersion và revision thành một số.
UPsert dùng setOnInsert nên existing v1 tự thành v2.
Sau khi count v1=0 một lần thì xóa mọi decoder v1,
kể cả trong công cụ restore backup cũ.
~~~

Hãy chỉ ra từng lỗi và viết lại kế hoạch kiểm thử đủ **schema validation, mixed-version read/write compatibility, dữ liệu lỗi, concurrency, migration, phục hồi và điều kiện contract phase**.

---

**Kết luận:** Kiểm thử schema validation trong NoSQL không dừng ở việc database chấp nhận một document đúng kiểu. Trong quá trình nâng cấp, **nhiều phiên bản dữ liệu và nhiều phiên bản ứng dụng cùng tồn tại**; do đó phải kiểm **reader/writer compatibility matrix, legacy missing version, null/type/enum/nested data, CRUD/UPSERT/PATCH/REPLACE, uniqueness, tenant isolation, CAS và migration/backfill/CDC**. Schema version mô tả định dạng, còn revision bảo vệ concurrent writes; cả hai không thay thế nhau. Nên triển khai **expand readers → cho phép mixed schema có kiểm soát → đổi writers → backfill và đối soát → chặn legacy writers → thu hẹp validator**, với negative fixtures, DB integration tests, property-based tests, shadow-read và observability. **Không coi “không ném exception”, “validator ở warn” hay “đếm bản ghi bằng nhau” là bằng chứng dữ liệu đúng**. Hệ chỉ an toàn khi mọi phiên bản được cam kết đều được hiểu đúng, mọi write path giữ bất biến và khả năng phục hồi từ dữ liệu lịch sử vẫn được chứng minh.
