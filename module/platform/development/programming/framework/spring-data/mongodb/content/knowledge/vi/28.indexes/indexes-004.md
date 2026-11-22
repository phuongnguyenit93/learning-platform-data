# Unique index, dữ liệu trùng và giá trị thiếu hoặc null

> **Chương:** Chỉ mục  
> **Module:** `SPRING_DATA_MONGODB` — dùng Spring Data MongoDB kết nối, ánh xạ document và thao tác dữ liệu bằng `MongoTemplate` hoặc repository; thực hành thiết kế truy vấn, aggregation, index, transaction, reactive access, kiểm thử và chẩn đoán hiệu năng dữ liệu.  
> **Mục tiêu:** Hiểu ràng buộc duy nhất ở MongoDB; phân biệt unique index một trường, compound unique, unique sparse và unique partial; giải thích đúng trường thiếu, BSON `null` và giá trị rỗng; phát hiện dữ liệu trùng trước khi xây index; áp dụng qua `@Indexed`/`@CompoundIndex` và `MongoTemplate.indexOps()`; kiểm thử lỗi `E11000`, cập nhật đồng thời và migration an toàn.

## 1. Tình huống nghiệp vụ: email không trùng nhưng có thể chưa được cung cấp

Giả sử hệ thống khách hàng cho phép tạo tài khoản **chưa có email**. Khi khách hàng nhập email hợp lệ, ứng dụng muốn bảo đảm không hai tài khoản trong cùng tenant dùng cùng một email đã chuẩn hóa.

Một định nghĩa nhìn có vẻ đơn giản:

~~~javascript
db.customers.createIndex(
  { email_norm: 1 },
  { unique: true }
);
~~~

Nhưng collection có thể chứa:

~~~javascript
{ _id: "c101", name: "An", email_norm: "an@example.test" }
{ _id: "c102", name: "Bình" }                    // thiếu email_norm
{ _id: "c103", name: "Chi", email_norm: null }   // có email_norm, giá trị null
{ _id: "c104", name: "Dũng" }                    // cũng thiếu email_norm
~~~

**Unique index một trường thông thường không cho phép tình trạng này**: cả trường **missing** và BSON `null` đều sinh khóa index mang giá trị `null`. Có nhiều hơn một document có khóa `null` sẽ khiến thao tác **tạo unique index thất bại** hoặc thao tác **ghi mới bị từ chối** nếu index đã tồn tại.

Đây không phải lỗi đặc thù Spring Data. Nó là **semantics phía MongoDB server**. `@Indexed(unique = true)` không biến `null` thành “bỏ qua kiểm tra duy nhất”.

### 1.1. Bốn câu hỏi phải trả lời trước khi tạo index

1. **Duy nhất theo phạm vi nào?** Toàn collection hay trong từng `tenantId`?
2. **Document chưa có giá trị** được phép tồn tại nhiều hay chỉ một?
3. **`null`, missing, `""`, chuỗi toàn khoảng trắng** có được coi là tương đương không?
4. **Chuẩn hóa/chữ hoa-thường** có tác động đến sự bằng nhau không?

Không có một lựa chọn `unique: true` duy nhất đáp ứng mọi chính sách trên. Phải chọn **khóa index**, **partial filter hoặc sparse**, **kiểu dữ liệu**, **collation** và **quy tắc chuẩn hóa** phù hợp.

## 2. Cơ chế unique index và những điều nó không đảm bảo

Unique index bảo đảm không có **hai document khác nhau** có cùng khóa index trong phạm vi ràng buộc. MongoDB mặc định tạo unique index cho trường `_id`.

~~~javascript
// Khóa duy nhất toàn collection:
db.customers.createIndex({ email_norm: 1 }, { unique: true });

// Khóa kết hợp duy nhất:
db.customers.createIndex(
  { tenant_id: 1, email_norm: 1 },
  { unique: true }
);
~~~

| Index | Điều kiện không được trùng | Trường hợp được phép |
| --- | --- | --- |
| `{email_norm:1}` unique | Email giống nhau trên toàn collection | Email khác nhau |
| `{tenant_id:1,email_norm:1}` unique | Cùng **cặp** tenant/email | Email giống nhau ở **hai tenant khác nhau** |
| `{email_norm:1}` unique sparse | Email giống nhau trong các document **có field email_norm** | Nhiều document thiếu field |
| `{email_norm:1}` unique partial với `$type:"string"` | Chuỗi email giống nhau trong document được index | Nhiều document missing/null nằm ngoài filter |

### 2.1. Unique là ràng buộc trên dữ liệu thật, không chỉ gợi ý cho optimizer

Index thường giúp truy vấn nhanh hơn. **Unique index còn từ chối write vi phạm duy nhất** khi insert, update hoặc upsert, kể cả khi lệnh ghi đi qua MongoDB Java Driver thay vì Spring Data repository.

Một lần `findByEmailNorm(...)` cho kết quả rỗng **không thay thế** unique index:

~~~text
Request A: find(email) -> chưa có
Request B: find(email) -> chưa có
Request A: insert(email) -> thành công
Request B: insert(email) -> nếu KHÔNG có unique index, cũng có thể thành công
~~~

Unique index bảo vệ ngay tại **bước ghi trên server**. Kiểm tra trước khi ghi vẫn hữu ích để đưa thông báo đẹp, nhưng phải có index mới ngăn race giữa các writer.

### 2.2. Unique không có nghĩa dữ liệu đã được làm sạch

Index **không tự xóa** document trùng đã tồn tại. Nếu collection chứa hai khóa vi phạm, `createIndex(..., {unique:true})` sẽ **thất bại**; phải xử lý dữ liệu và kiểm soát writer trước khi tạo thành công.

Unique index cũng **không thay thế**:

- Validation kiểu BSON (email phải là string, không phải array).
- Chuẩn hóa email, mã đơn, số điện thoại trước khi lưu.
- Phân quyền tenant.
- Ràng buộc quan hệ giữa các collection.
- Quy tắc “một khách hàng đã xác thực chỉ được một email đang hoạt động”.

## 3. Tự kiểm chứng: unique một trường với giá trị thiếu và null

Tất cả ví dụ dùng **collection thử nghiệm riêng** trong `spring_data_mongodb_lab`. Không chạy `drop()` trên collection ứng dụng thật.

### 3.1. Tạo collection chưa có unique index

~~~javascript
use spring_data_mongodb_lab

const legacy = db.customers_unique_legacy_004;

legacy.insertMany([
  { _id: "l401", tenant_id: "t01", email_norm: "an@example.test" },
  { _id: "l402", tenant_id: "t01", email_norm: "an@example.test" },
  { _id: "l403", tenant_id: "t01", email_norm: null },
  { _id: "l404", tenant_id: "t01" },
  { _id: "l405", tenant_id: "t02" },
  { _id: "l406", tenant_id: "t01", email_norm: "" }
]);
~~~

Collection này cố ý chứa hai loại dữ liệu có thể vi phạm:

- `l401/l402` trùng email thực.
- `l403` có email `null`, trong khi `l404/l405` **không có field** email.

`l406` có email là **chuỗi rỗng** `""`; giá trị này **không phải** BSON `null`. Nhưng nếu có thêm một document email `""`, unique index sẽ xem đó là khóa trùng chuỗi rỗng.

### 3.2. Thử tạo unique index và đọc lỗi

~~~javascript
legacy.createIndex(
  { email_norm: 1 },
  { unique: true, name: "ux_email_norm" }
);
// Dữ liệu hiện tại có khóa trùng -> index build thất bại,
// thường nhận E11000 duplicate key error.
~~~

Index không thể được xem là đã tạo thành công chỉ vì code đã gọi `createIndex`. Phải kiểm tra kết quả lệnh và metadata index:

~~~javascript
legacy.getIndexes();
// Kiểm tra có thực sự xuất hiện ux_email_norm với unique:true không.
~~~

**Chú ý:** những lệnh insert có ID cố định chỉ chạy một lần trên fixture sạch. Những ví dụ tiếp theo nên xem là các kịch bản độc lập; khi muốn chạy lại, dùng collection test mới hoặc dọn đúng document do bạn sở hữu.

### 3.3. Single-field unique: missing và null dùng cùng khóa index

Giả sử collection mới đã có unique index trên `email_norm`:

~~~javascript
const strict = db.customers_unique_strict_004;
strict.createIndex(
  { email_norm: 1 },
  { unique: true, name: "ux_email_strict" }
);

strict.insertOne({ _id: "s401", email_norm: "a@example.test" });
strict.insertOne({ _id: "s402", email_norm: null });

// Các thao tác SAU dự kiến thất bại nếu index còn nguyên:
strict.insertOne({ _id: "s403" });                 // missing -> null key
strict.insertOne({ _id: "s404", email_norm: null }); // explicit null
strict.insertOne({ _id: "s405", email_norm: "a@example.test" });
~~~

Sau `s402`, cả missing và explicit null mới đều xung đột với khóa `null` đã tồn tại. Nếu thử theo thứ tự ngược lại, document missing đầu tiên có thể chiếm khóa `null` và document explicit null sau đó thất bại. Điều kiện là **tối đa một document có khóa unique null**, không phải “tối đa một missing và thêm một null”.

### 3.4. Bảng kết quả của unique một trường

| Dữ liệu mới | Có unique field đơn, không sparse? | Lý do |
| --- | --- | --- |
| Một document email `"a@example.test"` | Có, nếu chưa tồn tại khóa đó | Giá trị riêng |
| Document thứ hai email `"a@example.test"` | **Không** | Trùng khóa string |
| Một document email missing | Có, nếu chưa có khóa null | Missing được index như null |
| Document thứ hai email missing | **Không** | Trùng khóa null |
| Một document email `null` sau missing | **Không** | Cùng khóa null |
| Một document email `""` | Có, nếu chưa có `""` | Empty string là một giá trị string |
| Document thứ hai email `""` | **Không** | Trùng chuỗi rỗng |

Đây là hành vi đáng nhớ khi model Java có `String email` nullable: nhiều entity có email Java `null` không có nghĩa MongoDB cho phép chúng đồng thời đi qua unique index không sparse.

## 4. Missing, null và chuỗi rỗng là ba trạng thái khác nhau

MongoDB phân biệt **field không có trong document**, **field có BSON null**, và **field có chuỗi rỗng**. Khi query, cần biết phép so sánh nào bao gồm trường hợp nào:

~~~javascript
// Khớp explicit null VÀ missing:
legacy.find({ email_norm: null });

// Chỉ trường không tồn tại:
legacy.find({ email_norm: { $exists: false } });

// Chỉ trường có kiểu BSON null:
legacy.find({ email_norm: { $type: "null" } });

// Có trường và chứa một string rỗng:
legacy.find({ email_norm: "" });
~~~

### 4.1. Trạng thái và tác động đến index

| BSON | `{email_norm:null}` | `{$exists:false}` | `{$type:"null"}` |
| --- | --- | --- | --- |
| Không có `email_norm` | Có | Có | Không |
| `email_norm:null` | Có | Không | Có |
| `email_norm:""` | Không | Không | Không |
| `email_norm:"an@example.test"` | Không | Không | Không |

`{email_norm:{$exists:true}}` khớp cả string và explicit null. Đây là lý do **`$exists:true` không phải điều kiện “email khác null”**.

### 4.2. `null` trong Java không đủ mô tả cách lưu BSON

Đối tượng Java:

~~~java
class Customer {
    private String emailNorm; // null
}
~~~

có thể được converter lưu thành field missing hoặc explicit BSON null tùy annotation/configuration/cách ghi. Nhưng **unique index một trường thông thường vẫn xem hai trường hợp đó như khóa null**. Khi cần phân biệt tại API, phải dùng hợp đồng dữ liệu rõ:

- **Missing:** khách hàng chưa cung cấp email.
- **Explicit null:** email đã được gỡ bỏ hoặc hệ thống chủ động lưu null.
- **Empty string:** chuỗi có độ dài 0; thường là dữ liệu đầu vào cần chuẩn hóa hoặc từ chối.

Trong hệ thống thực, nên **thống nhất một policy** thay vì để cả ba biểu diễn “không có email” một cách ngẫu nhiên.

### 4.3. Một số trạng thái đặc biệt khác

`"   "` (toàn khoảng trắng) cũng là **một string khác `""`** nếu chưa normalize. `"An@Example.test"` và `"an@example.test"` là hai chuỗi khác nhau dưới so sánh binary mặc định. Các giá trị số hoặc array không nên xuất hiện trong trường email nếu schema yêu cầu string.

Unique index không mặc nhiên validate quy tắc email hay coi các giá trị kể trên tương đương. Xác định chính sách chuẩn hóa và thêm validation của ứng dụng/MongoDB.

## 5. `unique + sparse`: bỏ qua missing, nhưng KHÔNG bỏ qua null

Sparse index trên **một trường** chỉ index những document **có trường ấy**. Khi kết hợp `unique:true`, giá trị trùng giữa các document được index vẫn bị từ chối.

~~~javascript
const sparse = db.customers_unique_sparse_004;

sparse.createIndex(
  { email_norm: 1 },
  {
    unique: true,
    sparse: true,
    name: "ux_email_sparse"
  }
);

sparse.insertOne({ _id: "p401" });                // thành công: missing
sparse.insertOne({ _id: "p402" });                // thành công: missing
sparse.insertOne({ _id: "p403", email_norm: null }); // thành công: null đầu tiên

// Những lệnh sau sẽ bị từ chối:
sparse.insertOne({ _id: "p404", email_norm: null });

sparse.insertOne({ _id: "p405", email_norm: "a@example.test" });
sparse.insertOne({ _id: "p406", email_norm: "a@example.test" });
// p405 thành công; p406 lỗi duplicate key.
~~~

**Điểm khác biệt:** nhiều document missing được phép, nhưng **chỉ tối đa một explicit null** đối với index unique sparse một trường (vì null vẫn được index).

### 5.1. Bảng quyết định: unique thông thường vs unique sparse

| Tình huống | Unique thường | Unique sparse một trường |
| --- | --- | --- |
| Nhiều document thiếu email | Không | **Có** |
| Nhiều document email explicit null | Không | Không |
| Nhiều document email `""` | Không | Không |
| Nhiều document cùng email hợp lệ | Không | Không |
| Document email khác nhau | Có | Có |

Nếu policy là **“cho phép nhiều customer thiếu email hoặc email null”**, chỉ bật `sparse:true` **chưa đủ**.

### 5.2. Sparse ảnh hưởng cả query plan

Index sparse không chứa các document thiếu trường. MongoDB thường không chọn nó cho một truy vấn có thể cần **cả các document missing**, vì dùng index đó sẽ cho kết quả thiếu. Ép `hint()` trên sparse index để count/find toàn collection có thể khiến kết quả không đầy đủ.

Index phục vụ hai nhiệm vụ: **ràng buộc ghi** và **tối ưu đọc**. Khi chọn sparse, cần đánh giá cả hai.

## 6. `unique + partialFilterExpression`: chỉ ràng buộc tập document mong muốn

Partial index cho phép index **chỉ các document khớp filter**. Với `unique:true`, ràng buộc duy nhất áp dụng **chỉ trên tập đã được index**.

### 6.1. Cho phép nhiều missing và explicit null

Một policy thông dụng:

> Chỉ những customer có `email_norm` là **BSON string** mới phải có email duy nhất; tài khoản thiếu email hoặc email null có thể cùng tồn tại.

~~~javascript
const partial = db.customers_unique_partial_004;

partial.createIndex(
  { email_norm: 1 },
  {
    name: "ux_email_nonnull_string",
    unique: true,
    partialFilterExpression: {
      email_norm: { $type: "string" }
    }
  }
);

partial.insertOne({ _id: "q401" });                  // missing
partial.insertOne({ _id: "q402" });                  // missing
partial.insertOne({ _id: "q403", email_norm: null }); // null
partial.insertOne({ _id: "q404", email_norm: null }); // null
partial.insertOne({ _id: "q405", email_norm: "a@example.test" });

// Lệnh sau thất bại do trùng string:
partial.insertOne({ _id: "q406", email_norm: "a@example.test" });
~~~

`$type:"string"` được MongoDB hỗ trợ trong partial filter. Document thiếu field hoặc có BSON null không thỏa nên không bị unique index này hạn chế số lượng.

**Cẩn trọng:** MongoDB `$type` query trên trường array có thể khớp khi **phần tử mảng** có kiểu chỉ định. Vì vậy policy “email bắt buộc là scalar string” nên kết hợp **schema validation** và model Java đúng kiểu, không chỉ dựa vào partial filter để chặn array/sai kiểu.

### 6.2. Không dùng `$exists:true` để loại null

Sai nếu mục tiêu là bỏ qua null:

~~~javascript
partialFilterExpression: {
  email_norm: { $exists: true }
}
~~~

Vì explicit null cũng là **field tồn tại**, filter này vẫn index null. Nếu collection có hai document explicit null, unique partial với filter này có thể gặp `E11000`.

So sánh:

| Filter | Missing | Explicit null | String |
| --- | --- | --- | --- |
| `{$exists:true}` | Bỏ qua | **Index** | Index |
| `{$type:"string"}` | Bỏ qua | Bỏ qua | **Index** |
| `{email_norm:"verified@example.test"}` | Bỏ qua | Bỏ qua | Chỉ email bằng giá trị đó |

Thường dùng `$type:"string"` để minh họa chính sách unique cho giá trị đã cung cấp, nhưng vẫn cần xử lý `""` và chuỗi khoảng trắng.

### 6.3. Partial unique cho tài khoản đang hoạt động

Một chính sách khác:

> Email chỉ cần duy nhất giữa các account `ACTIVE`; account `DELETED` được phép lưu email trùng trong lịch sử.

~~~javascript
db.customers_unique_active_004.createIndex(
  { tenant_id: 1, email_norm: 1 },
  {
    unique: true,
    name: "ux_active_tenant_email",
    partialFilterExpression: {
      status: "ACTIVE",
      email_norm: { $type: "string" }
    }
  }
);
~~~

Index này áp uniqueness cho cặp tenant/email **chỉ khi** status = ACTIVE và email là string.

Nếu bạn đổi một document DELETED thành ACTIVE, MongoDB phải tạo index entry mới. Nếu cặp tenant/email đó đã có account ACTIVE, thao tác **chuyển trạng thái cũng bị E11000**. Partial unique không phải một cơ chế chỉ chạy lúc insert; nó áp dụng cho **mọi write làm document đi vào/ra tập được index**.

### 6.4. Partial index và query coverage

MongoDB không dùng partial index cho truy vấn nếu làm vậy sẽ bỏ sót những document mà truy vấn cần. Ví dụ một index chỉ chứa `status:"ACTIVE"` sẽ không đủ để trả **tất cả** customer của tenant nếu query không hạn chế status.

~~~javascript
// Có thể phù hợp partial index:
db.customers_unique_active_004.find({
  tenant_id: "t01",
  status: "ACTIVE",
  email_norm: "a@example.test"
});

// Không mặc định phù hợp: bao gồm cả DELETED.
db.customers_unique_active_004.find({
  tenant_id: "t01"
});
~~~

Hãy dùng `explain("executionStats")` để kiểm chứng index planner trên workload thật, không ép `hint` thiếu cơ sở.

### 6.5. Sparse và partial không dùng chung trong một định nghĩa

MongoDB/Spring Data index definition **không cho kết hợp** `sparse:true` với `partialFilterExpression` trên cùng index theo kiểu “cộng hai điều kiện”. Chọn **một** chính sách. Partial thường biểu diễn được điều kiện tinh vi hơn sparse; cần kiểm thử đúng dữ liệu missing/null.

## 7. Compound unique index: duy nhất theo tổ hợp tenant và email

Trong multi-tenant application, “email duy nhất” thường có nghĩa:

~~~text
(tenant_id, email_norm) phải duy nhất
~~~

chứ không phải email duy nhất trên **mọi tenant**.

~~~javascript
const tenants = db.customers_unique_tenants_004;

tenants.createIndex(
  { tenant_id: 1, email_norm: 1 },
  {
    unique: true,
    name: "ux_tenant_email"
  }
);

tenants.insertOne({
  _id: "t401",
  tenant_id: "t01",
  email_norm: "an@example.test"
});

tenants.insertOne({
  _id: "t402",
  tenant_id: "t02",
  email_norm: "an@example.test"
});
// Thành công: cùng email, khác tenant.

tenants.insertOne({
  _id: "t403",
  tenant_id: "t01",
  email_norm: "an@example.test"
});
// E11000: trùng cặp (t01, an@example.test).
~~~

### 7.1. Compound unique không tự bỏ qua các phần tử null/missing

Nếu có:

~~~javascript
{ _id: "t404", tenant_id: "t01" }
{ _id: "t405", tenant_id: "t01", email_norm: null }
~~~

thì với unique compound thường, cả hai có cặp khóa tương đương:

~~~javascript
{ tenant_id: "t01", email_norm: null }
~~~

Chỉ một document trong collection có thể có **cặp khóa đó**, nếu chưa có cặp trùng. Tuy nhiên, tenant khác có thể có cặp `(t02, null)` vì **tổ hợp** khác.

Điểm chính là **compound unique kiểm tra tổ hợp khóa**, không yêu cầu mọi thành phần của khóa đều khác null.

### 7.2. Bẫy: unique sparse compound vẫn có thể index missing email

Một nhầm lẫn rất hay gặp:

~~~javascript
db.customers.createIndex(
  { tenant_id: 1, email_norm: 1 },
  { unique: true, sparse: true }
);
~~~

Người viết nghĩ sparse sẽ bỏ qua mọi document thiếu `email_norm`. Nhưng với **compound sparse index gồm các field tăng/giảm thông thường**, MongoDB index document nếu **ít nhất một trường trong khóa có mặt**.

Nếu `tenant_id` luôn tồn tại, hầu như mọi document vẫn có index entry, kể cả khi `email_norm` missing. Khi đó hai document cùng tenant thiếu email có thể cùng khóa `(t01, null)` và **vẫn vi phạm unique**.

**Kết luận:** Không dùng `unique+sparse` trên `(tenant_id,email_norm)` như cách mặc định để cho phép nhiều customer chưa có email trong một tenant.

### 7.3. Thiết kế đúng: compound unique partial

~~~javascript
db.customers_unique_tenant_partial_004.createIndex(
  { tenant_id: 1, email_norm: 1 },
  {
    unique: true,
    name: "ux_tenant_email_present",
    partialFilterExpression: {
      email_norm: { $type: "string" }
    }
  }
);
~~~

Policy đạt được:

- `t01 + a@example.test`: tối đa một document.
- `t02 + a@example.test`: được phép (tenant khác).
- `t01` thiếu email: nhiều document được phép.
- `t01` có email explicit null: nhiều document được phép.
- Chuỗi rỗng `""` **vẫn là string**, nên trong từng tenant chỉ tối đa một document có `""`, trừ khi validation chặn trước.

Nếu `tenant_id` có thể thiếu/null, cần chuẩn hóa/validate tenant riêng: một partial filter chỉ kiểm tra email **không** thay thế yêu cầu tenant hợp lệ, và các cặp khóa chứa tenant null vẫn có thể xảy ra.

## 8. Case-insensitive uniqueness, collation và chuẩn hóa

Index mặc định có thể phân biệt:

~~~text
An@Example.test
an@example.test
~~~

theo binary comparison. Nếu sản phẩm quy định hai giá trị trên là **cùng định danh email**, phải biểu diễn chính sách.

### 8.1. Hướng A: lưu khóa đã chuẩn hóa

Ví dụ ứng dụng có:

~~~javascript
{
  email: "An@Example.test",     // giá trị hiển thị
  email_norm: "an@example.test" // khóa dùng kiểm tra duy nhất
}
~~~

và unique index trên `email_norm`. Khi đó mọi write phải đi qua cùng logic normalize/validate.

**Lưu ý nghiệp vụ:** Quy tắc email local-part có thể phụ thuộc provider và chính sách hệ thống; đừng tự loại dấu chấm, dấu cộng hoặc chuẩn hóa Unicode một cách tùy ý. Hãy quy định chuẩn hóa một cách nhất quán và kiểm thử. Nếu không có policy, **không** tự cho rằng mọi email đều không phân biệt hoa thường ở mọi thành phần.

### 8.2. Hướng B: unique collation

MongoDB hỗ trợ collation để xác định cách so sánh chuỗi. Ví dụ case-insensitive theo locale:

~~~javascript
db.customers_collation_004.createIndex(
  { email: 1 },
  {
    unique: true,
    name: "ux_email_ci",
    collation: {
      locale: "en",
      strength: 2
    }
  }
);
~~~

Ở strength 2, phép so sánh thường bỏ qua khác biệt hoa/thường nhưng vẫn xét một số khác biệt khác theo locale. Quy tắc cụ thể tùy collation và chuỗi. Nếu hai email khác nhau chỉ bởi chữ hoa/thường, unique collation có thể ngăn document thứ hai.

Khi query muốn tận dụng index có collation này:

~~~javascript
db.customers_collation_004.find(
  { email: "AN@example.test" }
).collation({
  locale: "en",
  strength: 2
});
~~~

Nếu query không có collation tương thích, optimizer có thể không sử dụng index cho so sánh chuỗi như mong đợi. Cần phân biệt **quy tắc uniqueness của index** và **cách query so sánh chuỗi**.

### 8.3. Chọn một chiến lược rõ ràng

Không nên vừa normalize một kiểu, vừa tạo collation với kiểu so sánh khác nhưng không định nghĩa điều kiện tương đương. Một thay đổi policy normalize/collation có thể tạo ra **các khóa trùng mới** trong dữ liệu legacy và làm migration unique index thất bại.

## 9. Unique multikey index và array: giới hạn quan trọng

Trường được index có thể là array:

~~~javascript
db.accounts_arrays_004.createIndex(
  { aliases: 1 },
  { unique: true }
);
~~~

Unique multikey index ngăn **hai document khác nhau** chứa cùng một index key. Nhưng trong **cùng một document**, phần tử lặp có thể chỉ tạo một index entry:

~~~javascript
// Nếu collection chưa có alias "a":
db.accounts_arrays_004.insertOne({
  _id: "a401",
  aliases: ["a", "a", "b"]
});
// Unique multikey không dùng để bắt phần tử "a" lặp trong cùng document.
~~~

Thêm document:

~~~javascript
db.accounts_arrays_004.insertOne({
  _id: "a402",
  aliases: ["b", "c"]
});
// E11000 do alias "b" đã thuộc document khác.
~~~

Vì vậy **unique multikey không bảo đảm “array không có phần tử trùng trong cùng một document”**. Nếu nghiệp vụ yêu cầu điều đó, cần validation hoặc logic cập nhật như `$addToSet` (có những giới hạn riêng với object equality) và kiểm thử thích hợp.

MongoDB còn có các ràng buộc đối với compound multikey index khi nhiều indexed fields đồng thời là arrays; không tạo index trên “các mảng song song” rồi kỳ vọng server chấp nhận mọi schema. Chủ đề này khác bài toán email đơn trị và cần xem tài liệu multikey riêng.

## 10. Phát hiện duplicate trước khi xây unique index

Việc đổi một index non-unique hoặc một collection legacy sang unique cần bắt đầu từ **dữ liệu**, không phải annotation.

### 10.1. Tìm email trùng thật sự (chỉ kiểu string)

~~~javascript
legacy.aggregate([
  {
    $match: {
      email_norm: { $type: "string" }
    }
  },
  {
    $group: {
      _id: "$email_norm",
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } },
  { $sort: { count: -1, _id: 1 } }
]);
// Trên fixture: an@example.test có l401 và l402.
~~~

Đây là kiểm kê theo giá trị **đã lưu**. Nếu policy sẽ normalize email sang lowercase hoặc bỏ khoảng trắng, phải kiểm duplicate **theo khóa sẽ được dùng sau migration**, không chỉ theo chuỗi hiện tại.

### 10.2. Phát hiện cặp tenant + email trùng

~~~javascript
legacy.aggregate([
  { $match: { email_norm: { $type: "string" } } },
  {
    $group: {
      _id: {
        tenant: "$tenant_id",
        email: "$email_norm"
      },
      count: { $sum: 1 },
      ids: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } }
]);
~~~

Khi index mục tiêu là compound unique partial, phép kiểm kê phải cùng **phạm vi**: tenant + email (đã normalize) + chính sách partial filter. Không chỉ kiểm riêng email vì cùng email ở hai tenant có thể hợp lệ.

### 10.3. Tìm các giá trị thiếu và null

~~~javascript
// Các document thiếu hẳn trường:
legacy.find({ email_norm: { $exists: false } });

// Các document có BSON null rõ ràng:
legacy.find({ email_norm: { $type: "null" } });

// Tất cả document có email null hoặc missing:
legacy.find({ email_norm: null });
~~~

Với index single-field **không partial**, phải xem số lượng trong tập `email_norm:null` theo ngữ nghĩa unique null key. Với unique partial chỉ bao gồm string, các document missing/null có thể nằm ngoài phạm vi index, nhưng vẫn cần kiểm schema/policy nghiệp vụ.

### 10.4. Tránh nhóm null một cách thiếu diễn giải

~~~javascript
legacy.aggregate([
  {
    $group: {
      _id: "$email_norm",
      count: { $sum: 1 }
    }
  }
]);
~~~

Khi group trực tiếp một field missing và BSON null, bạn dễ nhận một nhóm `_id:null` và tưởng rằng tất cả đều là explicit null. Nếu muốn **phân loại**, tạo biểu thức `$type` trước khi group hoặc dùng hai truy vấn `$exists:false` và `$type:"null"` riêng.

## 11. Quy trình migration dữ liệu trùng trước khi bật ràng buộc

Một kế hoạch production hợp lý phải giải quyết **cả dữ liệu lịch sử lẫn các writer đang chạy**. Các bước minh họa dưới đây mang tính thiết kế; không tự động xóa dữ liệu trên production.

<escape>1.</escape> **Xác định hợp đồng duy nhất.** Chọn global unique hay tenant-scoped; email missing/null có được phép nhiều không; giá trị normalized là gì; account soft-deleted có tham gia không.

<escape>2.</escape> **Đánh giá collection và workload.** Xác định số document, index hiện có, sharding, replication, quyền tạo index, lưu lượng ghi, cửa sổ triển khai và khả năng rollback.

<escape>3.</escape> **Kiểm kê duplicate theo khóa tương lai.** Lấy báo cáo gồm `_id`, tenant, giá trị thô/đã chuẩn hóa, trạng thái và nguyên nhân trùng; tránh log PII không cần thiết.

<escape>4.</escape> **Quyết định cách giải quyết từng nhóm.** Merge tài khoản có được phép không? Có tham chiếu đơn hàng cần chuyển không? Document nào là canonical? Không tùy tiện `deleteMany`/giữ document đầu tiên mà không có quyết định nghiệp vụ.

<escape>5.</escape> **Triển khai validation/normalization trước.** Bảo đảm mọi writer mới tuân thủ policy; quản lý race trong giai đoạn chuyển tiếp, có thể cần cơ chế chặn ghi/maintenance window/điều phối thích hợp.

<escape>6.</escape> **Backfill có checkpoint.** Chia lô, ghi log nghiệp vụ, xử lý lỗi idempotent, kiểm các reference liên quan và không làm mất dữ liệu chỉ vì email trùng.

<escape>7.</escape> **Kiểm kê lại rồi tạo index.** Nếu `createIndex` trả `E11000`, không đánh dấu migration thành công. Dừng, tìm nhóm còn trùng hoặc writer mới đã tạo xung đột, xử lý rồi thử lại.

<escape>8.</escape> **Xác nhận metadata và hành vi.** Dùng `getIndexes()`, insert/update test có chủ đích, metric lỗi duplicate, và kiểm tra ứng dụng nhận exception hợp lý.

<escape>9.</escape> **Theo dõi sau triển khai.** Đảm bảo các luồng đăng ký, cập nhật email, upsert, kích hoạt account và job migration không bị lỗi không xử lý.

### 11.1. Không dùng "drop duplicates" tự động

Unique index MongoDB hiện đại không có tùy chọn đáng tin cậy kiểu “bật unique rồi server tự xóa bản ghi trùng”. Tính năng kiểu `dropDups` từ các API rất cũ đã không còn là cơ chế migration an toàn. Việc hợp nhất hai customer là **quyết định nghiệp vụ**, không phải chức năng tạo index.

### 11.2. Không sửa duplicate bằng `deleteMany` trên một khóa mà không review

Sai:

~~~javascript
// KHÔNG DÙNG trong production:
// db.customers.deleteMany({ email_norm: "an@example.test" });
~~~

Lệnh trên xóa cả record chuẩn lẫn record trùng. Cách đúng là lập danh sách canonical IDs, kiểm chứng liên kết và chỉ ghi thay đổi được phê duyệt, có backup/rollback strategy.

### 11.3. Ghi đồng thời trong lúc index build

Một truy vấn kiểm kê có thể sạch lúc 10:00 nhưng writer mới chèn duplicate trước lúc index tạo xong. Do đó cần kế hoạch **kiểm soát các write vi phạm trong migration**, chứ không xem một báo cáo count trước đó là bảo đảm.

Trong replica set/sharded cluster, cần dùng quy trình index build được MongoDB hỗ trợ và hiểu hạn chế của rolling index build. Không tự chạy một vòng tạo index trên từng node khi không bảo đảm dữ liệu và consistency theo hướng dẫn triển khai.

## 12. Java Spring Data: `@Indexed(unique = true)`

### 12.1. Entity có unique index một trường

~~~java
// CustomerDocument.java
package com.example.mongoindexes;

import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "customers_spring_index_004")
public class CustomerDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("email_norm")
    @Indexed(unique = true, name = "ux_email_norm_global")
    private String emailNorm;

    protected CustomerDocument() { }

    public CustomerDocument(
            String id, String tenantId, String emailNorm) {
        this.id = id;
        this.tenantId = tenantId;
        this.emailNorm = emailNorm;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getEmailNorm() { return emailNorm; }
}
~~~

Annotation `@Indexed(unique=true)` khai báo **ý định tạo unique index** trên field tương ứng. Vì entity có `@Field("email_norm")`, Spring Data biết field BSON là `email_norm` khi xử lý metadata index.

**Cảnh báo:** ví dụ này định nghĩa **global unique single-field**. Nó **không đáp ứng** policy “mỗi tenant một email, cho phép nhiều missing/null”. Hãy chọn đúng index theo yêu cầu; đừng copy annotation này vào sản phẩm nếu cần compound partial.

### 12.2. Auto index creation không mặc định bật

Từ Spring Data MongoDB **3.0**, tự động tạo index khi khởi động/đụng entity **được tắt mặc định** để tránh tác động ngoài ý muốn đến dữ liệu và hiệu năng. Chỉ thêm `@Indexed` **không phải bằng chứng server đã có unique index**.

Có hai chiến lược:

1. **Migration được điều phối** bằng lệnh tạo index trên database đã kiểm tra duplicate, phù hợp production.
2. **Index creation được cấu hình tường minh** qua Spring Data/`IndexResolver` trong môi trường và thời điểm phù hợp.

Nếu bật auto-index mà dữ liệu đã trùng, startup hoặc thao tác khởi tạo index có thể **thất bại**. Không coi điều này là lý do để xóa dữ liệu hay vô hiệu hóa exception mà bỏ qua uniqueness.

### 12.3. Annotation unique sparse

~~~java
@Field("email_norm")
@Indexed(
    name = "ux_email_sparse",
    unique = true,
    sparse = true
)
private String emailNorm;
~~~

Index này cho phép nhiều document **missing email field**, nhưng vẫn giới hạn **một explicit null** với unique sparse single-field. Chỉ dùng khi policy thật sự như vậy.

### 12.4. Annotation unique partial

~~~java
@Field("email_norm")
@Indexed(
    name = "ux_email_nonnull",
    unique = true,
    partialFilter = "{ 'email_norm': { '$type': 'string' } }"
)
private String emailNorm;
~~~

`partialFilter` là JSON expression cho MongoDB partial index. Dùng tên BSON đúng trong biểu thức filter và kiểm chứng index definition thực ở server. `@Indexed` không cho phép kết hợp `sparse=true` và `partialFilter` trong cùng annotation.

**Quan trọng:** ba khai báo annotation ở các mục 12.1–12.4 là **lựa chọn thay thế**, **không** đặt đồng thời lên cùng field và tạo nhiều unique index khác chính sách mà không có kế hoạch migration.

## 13. Compound unique và `@CompoundIndex`

Nếu policy cần unique theo tenant:

~~~java
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "customers_spring_tenant_004")
@CompoundIndex(
    name = "ux_tenant_email",
    def = "{ 'tenantId': 1, 'emailNorm': 1 }",
    unique = true
)
public class CustomerByTenant {
    @org.springframework.data.mongodb.core.mapping.MongoId(
        org.springframework.data.mongodb.core.mapping.FieldType.STRING)
    private String id;

    @org.springframework.data.mongodb.core.mapping.Field("tenant_id")
    private String tenantId;

    @org.springframework.data.mongodb.core.mapping.Field("email_norm")
    private String emailNorm;

    protected CustomerByTenant() { }
}
~~~

`@CompoundIndex` nằm trên class. `def` trong ví dụ sử dụng **property Java** để Spring Data mapping chuyển sang BSON `tenant_id/email_norm` khi resolve index definition. Hãy xác minh `getIndexes()` trong test/prod để tránh đặt nhầm đường dẫn khi ứng dụng có converter tùy biến.

**Cảnh báo:** compound unique **không tự bỏ qua null/missing**. Để áp policy optional email trong mỗi tenant, có thể:

- Thiết lập compound unique **partial** bằng migration MongoDB tường minh.
- Hoặc dùng IndexOperations/`Index` với filter, sau đó xác minh index options trên server.

Đừng mặc định chuyển sang `sparse=true` trên compound index vì tenant luôn tồn tại vẫn khiến nhiều document email missing bị index.

## 14. `MongoTemplate.indexOps()` để tạo index chủ động

### 14.1. Unique một trường qua Spring Data

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;

public void ensureEmailUniqueIndex(MongoTemplate template) {
    template.indexOps(CustomerDocument.class)
        .ensureIndex(
            new Index()
                .on("emailNorm", Sort.Direction.ASC)
                .unique()
                .named("ux_email_norm_global")
        );
}
~~~

`indexOps(CustomerDocument.class)` giúp Spring Data có metadata domain class và mapping field. Nhưng `ensureIndex(...)` chỉ thành công nếu dữ liệu hiện tại **không vi phạm** unique index. Lệnh cũng không đảm bảo tự biến một index đã có tên giống nhưng options khác thành index đúng policy — cần quản lý migration/metadata một cách tường minh.

### 14.2. Compound partial qua `Index` và `PartialIndexFilter`

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.Index;
import org.springframework.data.mongodb.core.index.PartialIndexFilter;
import org.springframework.data.mongodb.core.query.Criteria;

public void ensureOptionalTenantEmailIndex(
        MongoTemplate template) {
    Index unique = new Index()
        .on("tenantId", Sort.Direction.ASC)
        .on("emailNorm", Sort.Direction.ASC)
        .unique()
        .named("ux_tenant_email_present")
        .partial(
            PartialIndexFilter.of(
                Criteria.where("email_norm").type(2)
                // BSON type 2 = string.
            )
        );

    template.indexOps(CustomerDocument.class)
        .ensureIndex(unique);
}
~~~

Các tên trong `.on("tenantId")` và `.on("emailNorm")` là **property Java** được ánh xạ bằng metadata entity; khi dựng partial filter cần hiểu `PartialIndexFilter`/mapped options và xác minh BSON thật. Dùng `email_norm` trong filter để khớp trường BSON của fixture. Có thể dùng raw MongoDB migration nếu muốn tránh bất kỳ sự mơ hồ nào về mapping partial filter qua phiên bản Spring Data.

**Không dùng đồng thời index global unique `ux_email_norm_global` và index compound partial** nếu mục tiêu là cho phép cùng email ở hai tenant hoặc nhiều missing/null: index global sẽ tiếp tục chặn những trường hợp đó. Thay đổi chính sách index cần xem **mọi unique index đang tồn tại**.

### 14.3. Kiểm tra index metadata

Trong `mongosh`:

~~~javascript
db.customers_spring_index_004.getIndexes();
~~~

Kỳ vọng trường hợp global unique:

~~~javascript
{
  key: { email_norm: 1 },
  name: "ux_email_norm_global",
  unique: true
}
~~~

Với partial index phải nhìn thấy `partialFilterExpression`. Với compound phải thấy đúng `key: {tenant_id:1,email_norm:1}`. **Tên index không chứng minh options đúng**.

### 14.4. `IndexResolver` khi dùng annotation

Spring Data cung cấp `MongoPersistentEntityIndexResolver` để lấy definitions từ `@Indexed`, `@CompoundIndex` và các annotation khác. Một ứng dụng muốn điều phối tạo index theo metadata có thể:

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.index.IndexResolver;
import org.springframework.data.mongodb.core.index.MongoPersistentEntityIndexResolver;

public void resolveAndEnsure(MongoTemplate template) {
    var mappingContext =
        template.getConverter().getMappingContext();

    IndexResolver resolver =
        new MongoPersistentEntityIndexResolver(mappingContext);

    resolver.resolveIndexFor(CustomerDocument.class)
        .forEach(
            definition -> template
                .indexOps(CustomerDocument.class)
                .ensureIndex(definition)
        );
}
~~~

Đây là **minh họa cơ chế resolver**, không phải khuyến nghị tạo unique index cho production bất kỳ lúc nào mà không kiểm tra dữ liệu. Nếu startup tự tạo index từ annotation global unique nhưng dữ liệu đang vi phạm, ứng dụng có thể không khởi động được; migration index nên được điều phối.

## 15. Lỗi `E11000` và exception trong Java

Khi insert/update vi phạm unique constraint, MongoDB thường trả lỗi duplicate key với code **11000** và thông tin index/key vi phạm.

Ví dụ thông điệp (chỉ minh họa cấu trúc):

~~~text
E11000 duplicate key error collection: ...
index: ux_tenant_email_present
dup key: { tenant_id: "t01", email_norm: "an@example.test" }
~~~

Đừng parser chuỗi tiếng Anh thông điệp để quyết định nghiệp vụ — format có thể khác theo phiên bản server/driver hoặc cấu hình. Trong Spring Data, exception được dịch sang `org.springframework.dao.DuplicateKeyException` ở những luồng repository/`MongoTemplate` phù hợp.

### 15.1. Một service dùng catch ở tầng thích hợp

~~~java
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

@Service
public class CustomerRegistrationService {
    private final CustomerRepository repository;

    public CustomerRegistrationService(
            CustomerRepository repository) {
        this.repository = repository;
    }

    public CustomerDocument register(
            CustomerDocument newCustomer) {
        try {
            return repository.insert(newCustomer);
        } catch (DuplicateKeyException duplicate) {
            // Chuyển thành lỗi domain/API, ví dụ HTTP 409,
            // sau khi xác định đây đúng index nghiệp vụ được kỳ vọng.
            throw new CustomerEmailAlreadyUsedException(duplicate);
        }
    }
}
~~~

Trong đó `CustomerRepository` là `MongoRepository<CustomerDocument,String>`. `CustomerEmailAlreadyUsedException` là **exception miền do dự án tự định nghĩa** (chưa được khai báo trong đoạn ví dụ). Code tập trung minh họa xử lý lỗi và cần thêm lớp exception/domain mapping khi dùng thực.

**Không mặc định mọi `DuplicateKeyException` là email trùng**: cũng có thể là `_id` hoặc unique index khác. Trong production cần xác định constraint vi phạm bằng metadata lỗi có cấu trúc khi có sẵn, log an toàn và hướng xử lý tương ứng.

### 15.2. Check trước khi insert không đóng race

~~~java
if (!repository.existsByTenantIdAndEmailNorm(
        tenantId, emailNorm)) {
    repository.insert(customer);
}
~~~

Đoạn này có race giữa `exists` và `insert`. Unique index trên server mới ngăn việc hai writer cùng chèn khóa. Có thể giữ `exists` để cải thiện UX, nhưng **phải bắt lỗi duplicate tại write**.

### 15.3. Upsert và cập nhật email vẫn có thể xung đột

~~~javascript
db.customers_unique_tenant_partial_004.updateOne(
  { _id: "customer-123", tenant_id: "t01" },
  { $set: { email_norm: "an@example.test" } }
);
~~~

Nếu cặp `(t01, an@example.test)` đang thuộc customer khác, `$set` sẽ thất bại. Unique không chỉ áp lúc chèn.

Tương tự, `upsert:true` với filter không có khóa duy nhất/điều kiện đủ mạnh có thể tạo trùng logic dưới cạnh tranh. Unique index là tuyến phòng vệ, nhưng service vẫn cần idempotency/retry phù hợp và không retry mù mọi `E11000`.

## 16. Transaction, bulk writes và concurrency

### 16.1. Transaction không thay thế unique index

Một transaction MongoDB có thể giúp nhiều ghi all-or-nothing khi topology và driver hỗ trợ. Nhưng nếu hai transaction cùng cố tạo cặp tenant/email giống nhau, unique index vẫn là ràng buộc cuối cùng quyết định ghi nào được chấp nhận.

Đừng dựa vào `@Transactional` để bảo đảm duy nhất nếu database **không có unique constraint**. Kiểm tra trước rồi ghi trong transaction có thể còn rủi ro write skew hoặc yêu cầu isolation/lock khác; chính sách uniqueness nên được áp bằng index khi có thể.

### 16.2. Bulk import dữ liệu legacy

Khi bulk insert vào collection có unique index, một phần thao tác có thể thành công trước lỗi tùy ordered/unordered và transaction. Không giả định toàn bộ batch bị rollback khi một document duplicate.

Workflow import cần:

- Ghi nhận ID thành công và ID bị từ chối.
- Có retry idempotent cho các lỗi tạm thời.
- Phân biệt duplicate expected với lỗi kết nối/write concern.
- Không xóa dữ liệu trùng hiện hữu tự động.
- Test xử lý lỗi trong ordered/unordered bulk và trong transaction nếu dùng.

### 16.3. Unique index trên sharded collection

Sharding có các **hạn chế riêng** đối với việc tạo unique index: một unique index trên sharded collection thường phải có **shard key làm prefix** (trừ các ngoại lệ/chính sách cụ thể như index `_id`, cần xét vị trí áp uniqueness). Đừng giả định unique email global có thể tạo trên mọi sharded collection.

Trước khi thiết kế global uniqueness cho một hệ thống sharded, phải kiểm tra chính sách shard key, version MongoDB, cấu trúc index được phép và khả năng thực sự cưỡng chế uniqueness trên các shard.

MongoDB cũng **không hỗ trợ `unique` cho hashed index**. Nếu cần unique trên một khóa, không đơn giản chuyển nó thành hashed rồi đặt `unique:true`.

## 17. Case study: chính sách email theo tenant có dữ liệu thiếu

Yêu cầu:

> Một tenant có thể có nhiều customer chưa cung cấp email. Nếu email đã được cung cấp dưới dạng chuỗi hợp lệ, nó phải duy nhất **trong tenant đó**. Customer của tenant khác có thể dùng cùng email.

Thiết kế đề xuất gồm:

1. **Schema:** `tenant_id` bắt buộc, có kiểu string hợp lệ; `email_norm` là string chuẩn hóa hoặc missing/null theo chính sách; không cho phép array/object.
2. **Index:** compound unique partial `(tenant_id, email_norm)`, filter chỉ email string.
3. **Application:** normalize và validate email trước mọi insert/update; tenant lấy từ security context.
4. **Migration:** tìm duplicate theo chính khóa kết hợp **sau normalize**; làm sạch dữ liệu trước khi tạo index.
5. **Write handling:** bắt `DuplicateKeyException` có kiểm soát và trả conflict cho nghiệp vụ.
6. **Tests:** kiểm các tình huống nhiều missing/null, email giống nhau trong một tenant, giống nhau giữa hai tenant và update làm xung đột.

### 17.1. MongoDB index đúng policy

~~~javascript
db.customers_policy_004.createIndex(
  { tenant_id: 1, email_norm: 1 },
  {
    name: "ux_policy_tenant_email",
    unique: true,
    partialFilterExpression: {
      email_norm: { $type: "string" }
    }
  }
);
~~~

### 17.2. Bộ thử nghiệm hành vi

~~~javascript
const c = db.customers_policy_004;

c.insertOne({ _id: "x401", tenant_id: "t01" });
c.insertOne({ _id: "x402", tenant_id: "t01" });
// Nhiều missing: thành công.

c.insertOne({ _id: "x403", tenant_id: "t01", email_norm: null });
c.insertOne({ _id: "x404", tenant_id: "t01", email_norm: null });
// Nhiều explicit null: thành công.

c.insertOne({
  _id: "x405", tenant_id: "t01",
  email_norm: "an@example.test"
});
c.insertOne({
  _id: "x406", tenant_id: "t02",
  email_norm: "an@example.test"
});
// Cùng email khác tenant: thành công.

c.insertOne({
  _id: "x407", tenant_id: "t01",
  email_norm: "an@example.test"
});
// E11000: trùng trong cùng tenant.
~~~

### 17.3. Khi policy cho phép xóa email

Nếu khách hàng gỡ email, bạn có thể chọn:

~~~javascript
// Xóa field: document đi ra khỏi partial index:
c.updateOne({ _id: "x405" }, { $unset: { email_norm: "" } });

// Hoặc set null, cũng không thỏa partial $type:string:
c.updateOne({ _id: "x405" }, { $set: { email_norm: null } });
~~~

Chọn **một semantics nhất quán** cho “đã gỡ email”. Cả hai làm khóa string cũ không còn được giữ bởi index unique partial, nên một document khác có thể dùng email cũ. Nếu sản phẩm yêu cầu giữ email đã giải phóng trong một thời gian, phải thiết kế thêm **quy tắc reservation/history**; unique partial không tự “giữ chỗ”.

## 18. Integration test với MongoDB thật và Spring Data

Unit test mock `MongoRepository` không chứng minh MongoDB từ chối duplicate, cũng không kiểm index thật. Test cần dùng MongoDB test instance/Testcontainers và tạo index **trước khi insert dữ liệu**.

### 18.1. Ma trận kiểm thử bắt buộc

| Test | Kỳ vọng |
| --- | --- |
| Global unique, cùng email | Duplicate key |
| Global unique, missing rồi null | Chỉ một khóa null tổng cộng |
| Unique sparse, hai missing | Được phép |
| Unique sparse, hai explicit null | Duplicate key |
| Unique partial `$type:"string"`, hai missing | Được phép |
| Unique partial `$type:"string"`, hai null | Được phép |
| Unique partial, hai email string trùng | Duplicate key |
| Compound unique, cùng email khác tenant | Được phép |
| Compound unique, cùng tenant/email | Duplicate key |
| Compound sparse với tenant luôn có | Không được giả định bỏ qua missing email |
| Compound partial với missing email cùng tenant | Được phép |
| Update một customer sang email đã dùng | Duplicate key |
| Dùng `@Field("email_norm")` | Index tạo đúng field BSON |
| Auto index creation off | Annotation không đồng nghĩa index đã có |
| Insert qua `MongoTemplate` | `DuplicateKeyException` được dịch phù hợp |
| Normalize/collation | Những giá trị tương đương theo policy bị chặn |
| Index build trên legacy duplicate | Thất bại, không tự xóa dữ liệu |

### 18.2. Integration test minh họa cho unique partial

Test dùng **collection riêng**, dọn đúng ID do test tạo, và chỉ thực hiện trên MongoDB test cô lập.

~~~java
package com.example.mongoindexes;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.mongodb.client.model.Filters;
import com.mongodb.client.model.IndexOptions;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@DataMongoTest
class UniquePartialIndexTest {
    @Autowired MongoTemplate template;

    @org.springframework.data.mongodb.core.mapping.Document(
        collection = "customers_test_unique_004")
    static class TestCustomer {
        @MongoId(FieldType.STRING)
        private String id;

        @Field("email_norm")
        private String emailNorm;

        protected TestCustomer() { }

        TestCustomer(String id, String emailNorm) {
            this.id = id;
            this.emailNorm = emailNorm;
        }
    }

    @Test
    void partialUniqueAllowsMissingAndNullButRejectsDuplicateString() {
        var coll = template.getDb()
            .getCollection("customers_test_unique_004");
        List<String> ids = List.of(
            "fixture-u004-a",
            "fixture-u004-b",
            "fixture-u004-c",
            "fixture-u004-d",
            "fixture-u004-email",
            "fixture-u004-dup"
        );

        coll.createIndex(
            new org.bson.Document("email_norm", 1),
            new IndexOptions()
                .name("ux_test_email_string_004")
                .unique(true)
                .partialFilterExpression(
                    new org.bson.Document(
                        "email_norm",
                        new org.bson.Document("$type", "string")
                    )
                )
        );

        coll.deleteMany(Filters.in("_id", ids));
        try {
            coll.insertMany(List.of(
                new org.bson.Document("_id", ids.get(0)),
                new org.bson.Document("_id", ids.get(1)),
                new org.bson.Document("_id", ids.get(2))
                    .append("email_norm", null),
                new org.bson.Document("_id", ids.get(3))
                    .append("email_norm", null),
                new org.bson.Document("_id", ids.get(4))
                    .append("email_norm", "a@example.test")
            ));

            assertThat(coll.countDocuments(
                Filters.in("_id", ids.subList(0, 5))
            )).isEqualTo(5L);

            assertThatThrownBy(() ->
                template.insert(
                    new TestCustomer(
                        "fixture-u004-dup", "a@example.test")
                )
            ).isInstanceOf(DuplicateKeyException.class);

            assertThat(coll.countDocuments(
                Filters.eq("email_norm", "a@example.test")
            )).isEqualTo(1L);
        } finally {
            coll.deleteMany(Filters.in("_id", ids));
        }
    }
}
~~~

Trong ví dụ, class `TestCustomer` có mapping tới collection test nhưng **không dùng `@Indexed` tự động**; index được tạo bằng driver với options kiểm soát rõ. `MongoTemplate.insert(...)` thực hiện write qua Spring Data để quan sát `DuplicateKeyException` khi vi phạm.

**Lưu ý nhập code:** test dùng tên fully qualified `org.springframework.data.mongodb.core.mapping.Document` trên class để tránh xung đột với `org.bson.Document` dùng cho BSON; không import đồng thời hai annotation/class cùng tên đơn giản. Nên quản lý fixture/test database sao cho các test song song không dùng cùng collection/ID.

### 18.3. Test riêng cho compound partial

Dùng test collection `customers_policy_004` có index `{tenant_id:1,email_norm:1}` unique partial. Tạo:

~~~text
t01, missing                  -> PASS
t01, missing (document thứ 2) -> PASS
t01, null                     -> PASS
t01, null (document thứ 2)    -> PASS
t01, an@example.test          -> PASS
t02, an@example.test          -> PASS
t01, an@example.test lần 2    -> E11000
~~~

Kiểm **cả insert và update** sang khóa đã tồn tại. Nếu test chỉ chèn hai email khác nhau rồi kết luận unique hoạt động thì chưa xác minh được tình huống quan trọng nhất.

### 18.4. Kiểm index metadata bằng assert

Ngoài hành vi insert, kiểm `getIndexes()` có:

- `key` đúng: `email_norm` hoặc `tenant_id + email_norm`.
- `unique:true`.
- `partialFilterExpression` đúng filter được thiết kế.
- `collation` nếu sản phẩm dùng so sánh không phân biệt hoa thường.

Không chỉ assert tên index vì cùng tên nhưng cấu hình/options khác vẫn có thể không đáp ứng policy. Kiểm migration đã chạy và không còn một **global unique index khác** vô tình chặn trường hợp cross-tenant.

## 19. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không tạo được unique index | Collection đã có khóa trùng, kể cả missing/null | Aggregate kiểm duplicate theo chính khóa mục tiêu và giải quyết nghiệp vụ |
| Hai document thiếu email bị từ chối | Single-field unique không sparse | Xác định lại policy; cân nhắc partial unique |
| Unique sparse vẫn lỗi với nhiều null | Sparse index vẫn chứa field explicit null | Dùng partial filter loại null nếu policy cho phép |
| Compound unique sparse không cho hai missing email cùng tenant | Tenant field có mặt nên compound sparse vẫn index document | Dùng compound unique partial trên email string |
| `$exists:true` vẫn gặp duplicate null | Explicit null thỏa `$exists:true` | Dùng `$type:"string"` khi cần exclude null |
| Hai customer email `""` bị lỗi | Chuỗi rỗng là giá trị string thực | Validate/chuẩn hóa hoặc từ chối empty string |
| `An@...` và `an@...` cùng tồn tại | Index binary mặc định phân biệt hoa/thường | Normalize hoặc unique collation theo policy |
| Cùng email khác tenant bị từ chối | Đang có global unique index trên email | Chuyển sang compound unique theo tenant có migration |
| `@Indexed(unique=true)` không có tác dụng | Auto index creation mặc định off hoặc migration chưa chạy | Tạo index tường minh; kiểm `getIndexes()` |
| App startup lỗi sau bật auto-index | Dữ liệu legacy trùng | Dừng rollout, kiểm duplicate, xử lý trước index build |
| `save(entity)` bị `DuplicateKeyException` | Trùng `_id` hoặc một unique key khác | Xác định index/key vi phạm, không mặc định lỗi email |
| Update ACTIVE từ DELETED bị lỗi | Document bắt đầu tham gia partial unique index | Xử lý conflict trạng thái/email trong nghiệp vụ |
| Query không dùng partial index | Filter truy vấn không đảm bảo nằm trong partial set | Kiểm `explain()` và điều kiện query |
| Query có collation nhưng không tận dụng index | Collation query/index không tương thích | Đảm bảo dùng collation đúng với index |
| Unique multikey không bắt phần tử lặp trong cùng array | Unique áp giữa các document | Validation array riêng |
| Bulk import tạo được một phần rồi lỗi | Bulk không mặc định atomic toàn batch | Theo dõi per-item result, retry/idempotency và transaction nếu cần |
| Duplicate xuất hiện sau check `existsBy...` | Race giữa đọc và ghi | Unique index ở server + bắt lỗi tại write |
| Sharded collection không tạo được unique index tùy ý | Hạn chế shard-key prefix hoặc index type | Kiểm quy tắc sharding/index theo version |

## 20. Checklist trước khi triển khai unique index

1. **Viết rõ policy**: global, per-tenant, chỉ ACTIVE, hay chỉ email non-null.
2. **Quyết định semantics missing/null/empty** bằng dữ liệu và validation, không suy từ Java null.
3. **Chọn khóa index** một trường hay compound đúng phạm vi nghiệp vụ.
4. **Chọn sparse/partial đúng**; nhớ sparse một trường vẫn index explicit null, compound sparse có ngoại lệ quan trọng khi tenant có mặt.
5. **Chuẩn hóa string** bằng một chính sách nhất quán, xét collation nếu cần.
6. **Kiểm duplicate theo khóa tương lai**, bao gồm normalized values, tenant và partial filter.
7. **Không tự xóa/merge dữ liệu trùng**: phải có quyết định canonical, tham chiếu và kế hoạch rollback.
8. **Kiểm writer đồng thời** trong giai đoạn migration/build index.
9. **Không chỉ tin annotation**: xác minh index đã xuất hiện trên server và options đúng.
10. **Bắt `DuplicateKeyException` tại write**, không dựa vào pre-check tránh race.
11. **Test insert, update, upsert và bulk**, không chỉ test find.
12. **Đo ảnh hưởng index** tới write latency, dung lượng và hiệu năng query.
13. **Kiểm sharding và index type** trước khi chọn unique trong hệ phân tán.
14. **Theo dõi sau rollout**: lỗi E11000, request conflict, dữ liệu legacy và tác động tới tài khoản đang hoạt động.

## 21. Bài thực hành và đáp án

### Bài 1 — Hai trường thiếu email

Unique index `{email_norm:1}` không sparse đã tồn tại. Có thể insert **hai document đều không có `email_norm`** không?

**Đáp án:** Không. Missing tạo khóa index null; chỉ tối đa một document có khóa null. Document thứ hai vi phạm unique.

### Bài 2 — Missing và explicit null

Document A không có email, document B có `email_norm:null`. Với unique một trường thông thường, hai document cùng tồn tại được không?

**Đáp án:** Không. Cả hai sinh khóa null. Không có quota riêng cho missing và explicit null.

### Bài 3 — Unique sparse

Một unique sparse index đơn trên email cho phép bao nhiêu document missing? Cho phép bao nhiêu document explicit null?

**Đáp án:** Nhiều missing vì không được index; tối đa một explicit null vì null là field có mặt và được index.

### Bài 4 — Partial filter loại null

Viết index unique chỉ trên email dạng string.

**Đáp án:**

~~~javascript
db.customers.createIndex(
  { email_norm: 1 },
  {
    unique: true,
    partialFilterExpression: {
      email_norm: { $type: "string" }
    }
  }
);
~~~

Vẫn cần schema validation để ngăn array/object ngoài thiết kế và kiểm email `""`.

### Bài 5 — Vì sao `$exists:true` chưa đúng?

Filter partial `{email_norm:{$exists:true}}` có loại explicit null không?

**Đáp án:** Không. Null vẫn là field tồn tại nên document null được index và có thể gây duplicate key.

### Bài 6 — Unique theo tenant

`t01` và `t02` cùng email `"an@example.test"` có hợp lệ không nếu dùng unique compound `(tenant_id,email_norm)`?

**Đáp án:** Có. Ràng buộc dựa trên **tổ hợp**. Nhưng hai document trong cùng `t01` có cùng email sẽ bị từ chối.

### Bài 7 — Bẫy compound sparse

Vì sao `{tenant_id:1,email_norm:1}` với `unique:true,sparse:true` có thể vẫn từ chối hai customer trong t01 đều thiếu email?

**Đáp án:** Compound sparse gồm các field thường có thể index document nếu **ít nhất một indexed field tồn tại**. Vì tenant luôn có, cả hai được index với cặp `(t01,null)` và xung đột.

### Bài 8 — Case-insensitive

`"An@Example.test"` và `"an@example.test"` có luôn bị coi là trùng trong unique index bình thường không?

**Đáp án:** Không. Với default binary comparison, chúng là chuỗi khác nhau. Phải thiết kế normalization hoặc unique collation phù hợp với policy.

### Bài 9 — Duplicate trong legacy

Trước khi tạo unique index trên `email_norm` có 1 triệu document, nên chạy lệnh gì để phát hiện duplicate string?

**Đáp án:** Dùng aggregation `$match` kiểu string, `$group` theo email, `count` và `$match count > 1` như mục 10; lặp lại kiểm tra theo policy chuẩn hóa và khóa compound nếu có.

### Bài 10 — Migration an toàn

Hai customer cùng email đều có order/history. Có nên tự chọn customer đầu tiên rồi xóa customer thứ hai để tạo index không?

**Đáp án:** Không. Cần quyết định nghiệp vụ về canonical account, tham chiếu, audit, quyền truy cập, backup và rollback. Unique index không tự merge dữ liệu.

### Bài 11 — Spring Data annotation

Chỉ thêm `@Indexed(unique=true)` đã bảo đảm server tạo unique index ngay chưa?

**Đáp án:** Chưa. Spring Data MongoDB 3.0+ tắt auto index creation mặc định; cần migration/indexOps hoặc cấu hình tường minh và kiểm server index metadata.

### Bài 12 — Lỗi khi cập nhật

Đang có `(t01,an@example.test)`. Cập nhật email customer khác của t01 sang cùng giá trị sẽ thế nào?

**Đáp án:** Bị unique index từ chối như khi insert; thường có E11000 và được Spring Data dịch thành `DuplicateKeyException` khi đi qua API phù hợp.

### Bài 13 — Kiểm trước ghi

Hai request cùng thấy `existsByTenantIdAndEmailNorm(...) == false`. Có thể cả hai insert thành công nếu không có unique index không?

**Đáp án:** Có. Kiểm trước ghi có race. Database unique index mới là tuyến cưỡng chế chính.

### Bài 14 — Multikey

Một document có `aliases:["a","a"]`. Unique multikey có tự loại duplicate nội bộ không?

**Đáp án:** Không. Unique multikey áp ràng buộc **giữa document**, không bảo đảm không lặp phần tử trong cùng document.

### Bài 15 — Account ACTIVE

Unique partial chỉ index `status:"ACTIVE"`. Hai account DELETED cùng email có hợp lệ không? Nếu chuyển cả hai sang ACTIVE?

**Đáp án:** Hai DELETED nằm ngoài filter nên có thể cùng tồn tại. Khi chuyển sang ACTIVE, index kiểm uniqueness; không thể có cả hai cùng khóa ACTIVE nếu sẽ trùng nhau.

### Bài 16 — Một index global còn tồn tại

Bạn thêm unique compound partial theo tenant nhưng hệ thống vẫn có unique `{email_norm:1}` cũ. Hai tenant có thể dùng cùng email chưa?

**Đáp án:** Chưa, vì **global unique cũ vẫn còn cưỡng chế**. Phải kiểm toàn bộ index definitions và có migration loại/thay index theo kế hoạch an toàn; không tự động drop index trong ứng dụng production.

## Tài liệu tham khảo

- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/): unique đơn/compound, trường missing/null, dữ liệu trùng, multikey và hạn chế sharding.
- [MongoDB Manual — Sparse Indexes](https://www.mongodb.com/docs/manual/core/index-sparse/): sparse vs missing/null, compound sparse và kết hợp unique.
- [MongoDB Manual — Partial Indexes](https://www.mongodb.com/docs/manual/core/index-partial/): `partialFilterExpression`, unique partial, query coverage.
- [MongoDB Manual — Collation](https://www.mongodb.com/docs/manual/reference/collation/): so sánh chuỗi, locale và strength.
- [MongoDB Manual — `$type` Query Operator](https://www.mongodb.com/docs/manual/reference/operator/query/type/): kiểm kiểu BSON và hành vi khi field chứa array.
- [MongoDB Manual — Multikey Indexes](https://www.mongodb.com/docs/manual/core/indexes/index-types/index-multikey/): unique multikey và những giới hạn về indexed arrays.
- [MongoDB Manual — Index Builds on Populated Collections](https://www.mongodb.com/docs/manual/core/index-creation/): tạo index với collection có dữ liệu, vận hành và kiểm lỗi.
- [Spring Data MongoDB — Index Creation](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping-index-management.html): auto-index mặc định off, IndexResolver và IndexOperations.
- [Spring Data MongoDB — `@Indexed` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/Indexed.html): `unique`, `sparse`, `partialFilter`, `collation`.
- [Spring Data MongoDB — `@CompoundIndex` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/CompoundIndex.html): compound index và định nghĩa khóa.
- [Spring Data MongoDB — `Index` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/index/Index.html): fluent `on`, `unique`, `sparse`, `partial`.
- [Spring Data MongoDB — Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): `@Document`, `@Field`, `@MongoId` và kiểu BSON.
