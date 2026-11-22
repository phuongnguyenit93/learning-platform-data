# validationLevel, validationAction và xử lý document cũ trong MongoDB

## 1. Bài toán: schema mới gặp dữ liệu cũ

MongoDB cho phép các document trong cùng một collection có cấu trúc khác nhau. Tính linh hoạt này hữu ích khi phát triển nhanh hoặc thay đổi mô hình dữ liệu, nhưng cũng tạo rủi ro: một ứng dụng có thể ghi số tiền dưới dạng chuỗi, ứng dụng khác ghi dưới dạng Decimal128, hoặc một số document chưa có trường trạng thái bắt buộc.

Giả sử collection **orders** đã lưu hàng triệu document từ trước. Nhóm phát triển muốn áp dụng quy tắc mới:

- Mỗi đơn phải có **orderNo**, **tenantId**, **status**, **amount** và **placedAt**.
- status phải thuộc các giá trị **pending**, **paid**, **cancelled**.
- amount phải là BSON **Decimal128** và không âm.
- placedAt phải có kiểu BSON **Date**.

Vấn đề nằm ở chỗ một số đơn cũ thiếu status hoặc lưu amount bằng String. Nếu bật kiểm tra nghiêm ngặt ngay, ứng dụng có thể không cập nhật được các đơn cũ, kể cả khi chỉ muốn sửa một trường ghi chú không liên quan. Nếu cho qua mọi ghi sai cấu trúc, dữ liệu mới lại tiếp tục thiếu chuẩn.

MongoDB giải quyết việc áp dụng quy tắc bằng **collection validator** kết hợp với hai tùy chọn:

- **validationLevel:** quyết định **những thao tác/document nào bị áp dụng kiểm tra**.
- **validationAction:** quyết định **MongoDB xử lý ra sao khi thao tác được kiểm tra tạo ra document không hợp lệ**.

Hiểu riêng từng tùy chọn và hiểu **sự kết hợp** của chúng là điều cốt lõi khi bổ sung schema validation vào collection đã có dữ liệu.

## 2. Ba thành phần của collection validation

Định nghĩa minh họa:

~~~javascript
db.createCollection("orders", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderNo", "status", "amount"],
      properties: {
        orderNo: { bsonType: "string" },
        status: { enum: ["pending", "paid", "cancelled"] },
        amount: {
          bsonType: "decimal",
          minimum: NumberDecimal("0.00")
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
});
~~~

Khối cấu hình này được dùng khi **tạo collection mới**, nên trong thực hành cần chọn tên collection chưa tồn tại. Với collection có sẵn, dùng lệnh **collMod** ở mục sau để thay đổi validator mà không cần xóa collection.

| Thuộc tính | Câu hỏi được giải quyết | Ví dụ |
| --- | --- | --- |
| **validator** | Document hợp lệ phải có hình dạng/giá trị nào? | $jsonSchema yêu cầu status thuộc danh sách cho phép |
| **validationLevel** | MongoDB kiểm tra những thao tác/document nào? | strict, moderate, off; constraint từ MongoDB 9.0 |
| **validationAction** | Nếu không hợp lệ thì chặn hay chỉ cảnh báo? | error, warn; errorAndLog từ MongoDB 8.1 |

**$jsonSchema** là một cách phổ biến để khai báo kiểu BSON, trường bắt buộc, giá trị enum, giới hạn số và điều kiện trường. MongoDB còn hỗ trợ nhiều biểu thức truy vấn thích hợp làm validator. Schema validation là lớp bảo vệ dữ liệu ở database, không thay thế hoàn toàn validation nghiệp vụ hoặc kiểm soát quyền trong ứng dụng.

**Giá trị mặc định thông dụng:** nếu không chỉ định, validationLevel là **strict**, validationAction là **error**. Quy tắc chỉ được áp dụng khi có validator tương ứng; không nên suy luận rằng đặt strict mà không có quy tắc thì hệ thống tự hiểu cấu trúc nghiệp vụ.

## 3. validationLevel: chọn phạm vi kiểm tra

### 3.1. strict

**strict** áp dụng validator cho **mọi insert** và **mọi update**. Với một document đang vi phạm schema:

1. Document cũ **không tự bị xóa hay tự sửa** khi bật strict.
2. MongoDB chỉ kiểm tra document khi có thao tác ghi liên quan.
3. Nếu update tạo ra document vẫn không hợp lệ, việc chấp nhận hay từ chối phụ thuộc validationAction.
4. Nếu update đồng thời sửa đủ các lỗi để document sau cập nhật hợp lệ, thao tác có thể thành công ngay cả khi document trước cập nhật không hợp lệ.

Ví dụ document cũ:

~~~javascript
{
  _id: "old-001",
  orderNo: "SO-001",
  amount: NumberDecimal("150000.00")
  // Thiếu status.
}
~~~

Giả sử validator bắt buộc status, cấu hình strict + error sẽ chặn thao tác chỉ thêm note:

~~~javascript
db.orders.updateOne(
  { _id: "old-001" },
  { $set: { note: "Đã xác nhận địa chỉ" } }
);
~~~

Lý do không phải vì note sai, mà vì **document sau update vẫn thiếu status**. Nếu cùng lần update bổ sung status hợp lệ, kết quả sẽ đáp ứng validator.

strict thích hợp sau khi nhóm đã xử lý những dữ liệu sai cấu trúc và muốn tất cả lần ghi tiếp theo phải tuân theo quy tắc.

### 3.2. moderate

**moderate** vẫn kiểm tra **mọi insert**. Đối với update, MongoDB áp dụng validator cho những document **đã hợp lệ theo schema hiện tại trước khi update**; thao tác update trên document **đang không hợp lệ** không bắt buộc vượt qua kiểm tra đó.

Điều này mang lại khả năng chuyển tiếp:

- Document mới vẫn bị ràng buộc, nếu kết hợp với validationAction **error**.
- Document cũ đã đúng schema không được sửa thành sai schema.
- Document cũ đang sai schema vẫn có thể được cập nhật trong thời gian migration, dù thao tác đó chưa sửa hết lỗi.

Ví dụ cùng document thiếu status ở trên:

~~~javascript
db.orders.updateOne(
  { _id: "old-001" },
  { $set: { note: "Đã xác nhận địa chỉ" } }
);
~~~

Với **moderate + error**, thao tác này có thể thành công vì document trước update vốn không khớp schema và không bị áp dụng kiểm tra khi update.

Điểm cần tránh hiểu sai: **moderate không có nghĩa là chỉ cảnh báo**, cũng không có nghĩa là bỏ qua mọi document cũ. Nó phân biệt **trạng thái hợp lệ của document hiện có** trước update. Một document cũ đã hợp lệ vẫn bị kiểm tra khi cập nhật; một document đang sai vẫn có thể tiếp tục sai nếu không được sửa. Vì vậy moderate là **cơ chế tương thích quá độ**, không phải kế hoạch làm sạch dữ liệu tự động.

### 3.3. off

**off** tắt áp dụng schema validation đối với insert và update. Validator có thể vẫn được lưu trong metadata collection, nhưng MongoDB không thực thi kiểm tra theo validator khi validationLevel là off.

Ví dụ thay đổi cấu hình:

~~~javascript
db.runCommand({
  collMod: "orders",
  validationLevel: "off"
});
~~~

off có thể hữu ích trong tình huống migration được kiểm soát, nhưng làm mất hàng rào bảo vệ ở database. Không nên chuyển sang off chỉ để che một lỗi thiết kế schema hoặc một lỗi ghi dữ liệu kéo dài.

### 3.4. constraint trên MongoDB 9.0 trở lên

**MongoDB 9.0** bổ sung mức **constraint**. Mức này kiểm tra mọi insert/update **và bảo đảm toàn collection tuân thủ validator**: khi nâng cấp một collection có sẵn lên constraint, MongoDB quét các document hiện tại và không cho nâng cấp nếu có document sai schema.

constraint có thêm các điều kiện:

- validationAction phải là **error** hoặc **errorAndLog**.
- Không thể bypass document validation khi đang ở constraint.
- Không sửa validator trực tiếp trong lúc đang ở constraint; cần hạ về strict để đổi quy tắc, rồi thực hiện quy trình nâng cấp lại.
- Quá trình quét collection khi nâng cấp có thể tốn tài nguyên đáng kể với dữ liệu lớn.

Với collection đã tồn tại, quy trình nâng cấp thông thường bắt đầu từ strict, chạy collMod với **prepareConstraintValidationLevel: true**, sau đó mới đổi validationLevel sang constraint. Chỉ thực hiện khi phiên bản server hỗ trợ; các ví dụ thực hành chính của bài dùng strict/moderate/off để tương thích với nhiều bản MongoDB.

### 3.5. So sánh các mức

| validationLevel | Insert mới | Update document hiện đang hợp lệ | Update document hiện đang không hợp lệ | Kiểm tra dữ liệu cũ ngay khi bật? |
| --- | --- | --- | --- | --- |
| **off** | Không kiểm tra | Không kiểm tra | Không kiểm tra | Không |
| **moderate** | Có kiểm tra | Có kiểm tra | Không bắt buộc kiểm tra | Không |
| **strict** | Có kiểm tra | Có kiểm tra | Có kiểm tra | Không |
| **constraint (9.0+)** | Có kiểm tra | Có kiểm tra | Có kiểm tra | **Có** khi nâng cấp collection và phải PASS |

Trong bảng, “có kiểm tra” chỉ nói về việc áp dụng validator. **Kết quả kiểm tra không đạt có chặn thao tác hay không còn phụ thuộc validationAction**. Ngay cả khi validationLevel là off, những ràng buộc khác như unique index, _id bất biến, quyền truy cập vẫn tồn tại.

## 4. validationAction: xử lý thao tác vi phạm

### 4.1. error

**error** là hành động mặc định. Nếu một thao tác thuộc phạm vi kiểm tra tạo ra document không hợp lệ, MongoDB **từ chối thao tác ghi**. Ứng dụng thường nhận lỗi có mã **121 (DocumentValidationFailure)**.

~~~javascript
db.runCommand({
  collMod: "orders",
  validationAction: "error"
});
~~~

Đây là lựa chọn phù hợp khi muốn ngăn document mới hoặc document được cập nhật đi lệch khỏi schema. Cần kiểm thử tương thích tất cả luồng ghi trước khi bật trên collection sản xuất.

### 4.2. warn

**warn** cho phép thao tác vi phạm validator được tiếp tục và ghi thông tin cảnh báo vào **MongoDB server log**. Tùy hệ thống quan sát log, người gọi lệnh có thể chỉ thấy thao tác thành công; không được suy luận rằng mỗi warning đều xuất hiện như thông báo ngay trong mongosh hoặc response API.

~~~javascript
db.runCommand({
  collMod: "orders",
  validationAction: "warn"
});
~~~

warn hữu ích để **quan sát trước khi chặn**: nhóm có thể ghi nhận đường nào đang phát sinh document sai cấu trúc, triển khai sửa ứng dụng, rồi chuyển sang error. Nhưng warn **không làm dữ liệu trở nên hợp lệ** và không bảo đảm hết lỗi dữ liệu. Vẫn cần truy vấn/đếm các document đang sai schema.

### 4.3. errorAndLog từ MongoDB 8.1

Kể từ **MongoDB 8.1**, có thể dùng **errorAndLog** để **từ chối thao tác vi phạm và ghi lỗi vào mongod log**. Đây là lựa chọn hữu ích khi cần vừa enforcement vừa quan sát server log.

~~~javascript
// Chỉ dùng trên MongoDB 8.1+.
db.runCommand({
  collMod: "orders",
  validationAction: "errorAndLog"
});
~~~

Không cấu hình giá trị này trên phiên bản chưa hỗ trợ. Khi có kế hoạch hạ cấp MongoDB, cần xem xét tương thích với cấu hình errorAndLog trước; thay đổi cấu hình có thể là điều kiện cần để downgrade.

### 4.4. Ma trận kết hợp

| validationLevel + validationAction | Insert sai | Update document hợp lệ thành sai | Update document cũ vốn sai và vẫn sai |
| --- | --- | --- | --- |
| **strict + error** | Bị từ chối | Bị từ chối | Bị từ chối |
| **strict + warn** | Được phép, có warning log | Được phép, có warning log | Được phép, có warning log |
| **moderate + error** | Bị từ chối | Bị từ chối | Được phép do update không thuộc phạm vi validation |
| **moderate + warn** | Được phép, có warning log | Được phép, có warning log | Được phép; update không bị kiểm tra bởi mức moderate |
| **off + error/warn** | Không kiểm tra schema | Không kiểm tra schema | Không kiểm tra schema |
| **constraint + error (9.0+)** | Bị từ chối | Bị từ chối | Không thể còn document sai schema nếu nâng cấp thành công |

Với **errorAndLog**, kết quả chặn giống error và có thêm ghi log cho vi phạm được kiểm tra. Với **constraint**, chỉ error hoặc errorAndLog là hợp lệ.

Một điểm dễ nhầm: **validationAction không mở rộng phạm vi kiểm tra**. Chọn error ở mức moderate không làm MongoDB bắt đầu kiểm tra mọi update vào document legacy đang sai. Ngược lại, warn ở mức strict vẫn chạy validator cho tất cả insert/update, nhưng chấp nhận document vi phạm.

## 5. Vì sao bật schema mới không sửa document cũ?

Khi dùng collMod thêm validator, MongoDB thay đổi **quy tắc cho những thao tác ghi tương lai**. Ở strict hoặc moderate, lệnh này không tự quét và sửa tất cả document đã lưu. Do đó:

- Document thiếu trường bắt buộc vẫn tồn tại.
- Document có amount dạng String vẫn giữ kiểu cũ.
- Những truy vấn đọc thường vẫn trả về các document đó.
- Một thao tác update về sau có thể bị chặn ở strict + error nếu document sau update chưa hợp lệ.
- Nếu một ứng dụng không chạm tới document cũ, document đó có thể tồn tại sai schema rất lâu.

Đây là lý do không được coi “collMod thành công” là bằng chứng toàn collection đã được chuẩn hóa. Muốn biết số lượng document đang sai, cần **truy vấn chính các document không khớp validator**.

### 5.1. Chuyển đổi schema mà không mất dữ liệu

Với một collection chứa các thế hệ document, kế hoạch chuyển đổi thường gồm:

1. Xây dựng validator phản ánh schema mục tiêu, xét kỹ kiểu BSON thực tế (String, Decimal128, Date, Array...).
2. Đo số lượng và nhóm nguyên nhân vi phạm trên dữ liệu hiện tại.
3. Đánh giá các phiên bản ứng dụng hoặc job nào vẫn ghi dữ liệu theo schema cũ.
4. Áp dụng chế độ phù hợp để quan sát/chuyển tiếp mà không làm gián đoạn luồng ghi quan trọng.
5. Viết migration **có thể chạy lại**, giới hạn phạm vi, ghi nhật ký số document được sửa, và tránh suy diễn giá trị thiếu.
6. Đối chiếu lại số document sai, sửa ứng dụng, rồi chuyển dần sang mức enforcement mạnh hơn.

Việc sửa dữ liệu có thể cần nhiều bước tùy quy tắc nghiệp vụ. Chẳng hạn, thiếu status có thể được suy ra đáng tin từ lịch sử thanh toán, nhưng không nên tùy tiện đặt tất cả về paid. Nếu không có cơ sở suy ra, cần quy tắc xử lý riêng hoặc hàng đợi rà soát thủ công.

## 6. Lab mongosh: tạo legacy data và quan sát moderate/strict

Để nhìn thấy chính xác hành vi, ta dùng database **mongo_validation_lab** và collection **lab_orders_legacy**. Collection này dành riêng cho bài thực hành. Script dưới đây cố định _id để có thể chạy lại; chỉ xóa document gắn **dataset: "schema-legacy-v1"**. Không chạy trên database hoặc collection dùng chung cho dữ liệu thật.

### 6.1. Tạo ba document: một hợp lệ, hai document legacy sai

Sao chép toàn bộ đoạn sau vào mongosh. Nếu collection chưa tồn tại, script tạo collection. Tiếp đó đặt validationLevel thành off để nạp dữ liệu mô phỏng trước khi có quy tắc; cuối cùng chuyển sang **moderate + error**.

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_validation_lab");
  const name = "lab_orders_legacy";
  const tag = "schema-legacy-v1";

  const validator = {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "dataset", "tenantId", "orderNo",
        "status", "amount", "placedAt"
      ],
      properties: {
        dataset: { enum: [tag] },
        tenantId: { bsonType: "string", minLength: 1 },
        orderNo: { bsonType: "string" },
        status: { enum: ["pending", "paid", "cancelled"] },
        amount: {
          bsonType: "decimal",
          minimum: NumberDecimal("0.00")
        },
        placedAt: { bsonType: "date" }
      }
    }
  };

  if (!lab.getCollectionNames().includes(name)) {
    lab.createCollection(name);
  }

  const orders = lab.getCollection(name);

  function setValidation(level, action) {
    const outcome = lab.runCommand({
      collMod: name,
      validator: validator,
      validationLevel: level,
      validationAction: action
    });
    if (outcome.ok !== 1) {
      throw new Error("collMod thất bại: " + JSON.stringify(outcome));
    }
  }

  // Mô phỏng giai đoạn collection chưa được áp validation.
  setValidation("off", "error");
  orders.deleteMany({ dataset: tag });

  orders.insertMany([
    {
      _id: "old-missing-status",
      dataset: tag,
      tenantId: "tenant-01",
      orderNo: "SO-LEGACY-001",
      amount: NumberDecimal("120000.00"),
      placedAt: ISODate("2025-11-01T08:00:00.000Z")
      // Thiếu status.
    },
    {
      _id: "old-wrong-amount",
      dataset: tag,
      tenantId: "tenant-01",
      orderNo: "SO-LEGACY-002",
      status: "pending",
      amount: "50000.00", // String, không phải Decimal128.
      placedAt: ISODate("2025-11-02T08:00:00.000Z")
    },
    {
      _id: "current-valid",
      dataset: tag,
      tenantId: "tenant-01",
      orderNo: "SO-2026-001",
      status: "paid",
      amount: NumberDecimal("98000.00"),
      placedAt: ISODate("2026-01-10T08:00:00.000Z")
    }
  ]);

  // Bật validator để bảo vệ insert và update của document đã hợp lệ.
  setValidation("moderate", "error");

  print("Tổng document của lab: " +
    orders.countDocuments({ dataset: tag }));
  print("Document chưa hợp lệ: " +
    orders.countDocuments({
      dataset: tag,
      $nor: [validator]
    }));
})();
~~~

**Kết quả mong đợi:** tổng số document của bộ dữ liệu là **3**; trong đó **2** document không hợp lệ. Bộ dữ liệu chứa:

| _id | Tình trạng | Vi phạm |
| --- | --- | --- |
| old-missing-status | Không hợp lệ | Thiếu status bắt buộc |
| old-wrong-amount | Không hợp lệ | amount là String thay vì Decimal128 |
| current-valid | Hợp lệ | Đầy đủ trường và kiểu BSON đúng |

Quy tắc cho amount là **decimal** có chủ đích: một giá trị NumberInt hoặc String dù có nội dung “50000” vẫn không khớp yêu cầu BSON Decimal128. Trong MongoDB, schema validation xét **kiểu dữ liệu thực tế**, không chỉ cách giá trị hiển thị trên màn hình.

### 6.2. Quan sát moderate + error

Chạy đoạn sau khi đã hoàn tất mục 6.1:

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_validation_lab")
    .getCollection("lab_orders_legacy");

  function attempt(label, operation) {
    try {
      const result = operation();
      print(label + ": THÀNH CÔNG");
      printjson(result);
    } catch (error) {
      print(label + ": BỊ TỪ CHỐI");
      print("code=" + error.code + ", message=" + error.message);
    }
  }

  // A. Insert sai: phải bị từ chối.
  attempt("A - insert thiếu status", () => orders.insertOne({
    _id: "new-invalid",
    dataset: "schema-legacy-v1",
    tenantId: "tenant-01",
    orderNo: "SO-2026-002",
    amount: NumberDecimal("45000.00"),
    placedAt: ISODate("2026-01-11T08:00:00.000Z")
  }));

  // B. Update từ một document hợp lệ thành không hợp lệ: bị từ chối.
  attempt("B - sửa amount của valid thành String", () => orders.updateOne(
    { _id: "current-valid" },
    { $set: { amount: "98000.00" } }
  ));

  // C. Update một document vốn đang thiếu status:
  // moderate bỏ qua kiểm tra với document đang sai.
  attempt("C - ghi note vào legacy đang sai", () => orders.updateOne(
    { _id: "old-missing-status" },
    { $set: { migrationNote: "Đang rà soát" } }
  ));
})();
~~~

Kết quả mong đợi:

- **A:** bị từ chối vì insert mới phải được kiểm tra.
- **B:** bị từ chối vì document trước update hợp lệ nhưng document sau update sai.
- **C:** thành công vì document legacy vốn không hợp lệ nên update này không bị moderate buộc kiểm tra.

Sau C, document old-missing-status **vẫn không hợp lệ**. Đây là minh họa rõ nhất rằng **moderate + error ngăn nhiều lỗi mới nhưng không tự sửa lỗi cũ**.

### 6.3. Chuyển sang strict + error

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_validation_lab");
  const change = lab.runCommand({
    collMod: "lab_orders_legacy",
    validationLevel: "strict",
    validationAction: "error"
  });
  printjson(change);

  const orders = lab.getCollection("lab_orders_legacy");

  print("Legacy còn tồn tại: " +
    orders.countDocuments({ _id: "old-missing-status" }));

  try {
    orders.updateOne(
      { _id: "old-missing-status" },
      { $set: { migrationNote: "Chỉ sửa ghi chú" } }
    );
    print("Không mong đợi: update thành công");
  } catch (error) {
    print("Strict đã chặn update legacy: code=" + error.code);
  }
})();
~~~

Kết quả mong đợi: old-missing-status **vẫn tồn tại** sau collMod; nhưng update chỉ thêm ghi chú bị chặn vì post-image vẫn thiếu status. Bật strict không phải là một bước migration dữ liệu cũ.

### 6.4. Chuyển sang strict + warn để quan sát

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_validation_lab");
  printjson(lab.runCommand({
    collMod: "lab_orders_legacy",
    validationLevel: "strict",
    validationAction: "warn"
  }));

  const result = lab.getCollection("lab_orders_legacy").updateOne(
    { _id: "old-missing-status" },
    { $set: { migrationNote: "Cảnh báo để quan sát" } }
  );
  printjson(result);
})();
~~~

Update sẽ **được phép** theo chính sách warn dù document vẫn thiếu status. Nếu thao tác bị kiểm tra và vi phạm, MongoDB ghi cảnh báo ở **server log**; việc nhìn thấy cảnh báo còn phụ thuộc cách triển khai và quyền quan sát log. Không nên coi kết quả acknowledged của update là bằng chứng schema đã đúng.

Nếu collection có unique index hoặc các ràng buộc khác, một thao tác vẫn có thể thất bại vì các ràng buộc đó dù validationAction là warn.

### 6.5. Tìm document không hợp lệ trước khi migrate

MongoDB hỗ trợ truy vấn **$jsonSchema** như một predicate. Ghép với **$nor** để chọn document **không khớp** schema.

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_validation_lab");
  const tag = "schema-legacy-v1";

  const validator = {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "dataset", "tenantId", "orderNo",
        "status", "amount", "placedAt"
      ],
      properties: {
        dataset: { enum: [tag] },
        tenantId: { bsonType: "string", minLength: 1 },
        orderNo: { bsonType: "string" },
        status: { enum: ["pending", "paid", "cancelled"] },
        amount: {
          bsonType: "decimal",
          minimum: NumberDecimal("0.00")
        },
        placedAt: { bsonType: "date" }
      }
    }
  };

  const orders = lab.getCollection("lab_orders_legacy");
  const invalidFilter = {
    dataset: tag,
    $nor: [validator]
  };

  print("Số document sai schema: " +
    orders.countDocuments(invalidFilter));

  printjson(
    orders.find(
      invalidFilter,
      { _id: 1, orderNo: 1, status: 1, amount: 1 }
    ).toArray()
  );
})();
~~~

Lúc này kết quả dự kiến vẫn là **2 document sai schema**. Điều kiện **$nor: [validator]** được đánh giá ở lúc truy vấn; nó không phụ thuộc validationLevel hay validationAction hiện đang chặn/cho phép write như thế nào.

Trong hệ thống thật, nên thống kê theo **loại lỗi** và phạm vi dữ liệu thay vì lấy toàn bộ hàng triệu document vào bộ nhớ client. Với collection lớn, cần batch theo _id, lập kế hoạch tài nguyên và tránh dùng toArray không giới hạn. Nếu collection dùng validator gồm nhiều biểu thức khác nhau, truy vấn kiểm kê cần sử dụng **đúng rule hiện hành**.

### 6.6. Sửa dữ liệu cũ rồi bật enforcement

Trong bộ dữ liệu mẫu, ta **biết rõ** cách khôi phục hai giá trị:

- old-missing-status tương ứng một đơn chưa thanh toán, nên status hợp lệ của ví dụ là pending.
- old-wrong-amount có chuỗi thập phân “50000.00”, có thể chuyển có chủ đích thành Decimal128 mà không thay đổi giá trị.

Ở dữ liệu thật, không được đoán trạng thái hoặc đơn giá; phải dùng nguồn nghiệp vụ đáng tin cậy và lưu bằng chứng chuyển đổi.

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_validation_lab");
  const orders = lab.getCollection("lab_orders_legacy");
  const tag = "schema-legacy-v1";

  // Khóa chặn lỗi mới trong ví dụ, sửa trực tiếp từng document
  // để post-image của từng update đáp ứng validator.
  printjson(lab.runCommand({
    collMod: "lab_orders_legacy",
    validationLevel: "strict",
    validationAction: "error"
  }));

  printjson(orders.updateOne(
    { _id: "old-missing-status", dataset: tag },
    { $set: { status: "pending" } }
  ));

  printjson(orders.updateOne(
    { _id: "old-wrong-amount", dataset: tag },
    { $set: { amount: NumberDecimal("50000.00") } }
  ));

  const validator = {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "dataset", "tenantId", "orderNo",
        "status", "amount", "placedAt"
      ],
      properties: {
        dataset: { enum: [tag] },
        tenantId: { bsonType: "string", minLength: 1 },
        orderNo: { bsonType: "string" },
        status: { enum: ["pending", "paid", "cancelled"] },
        amount: {
          bsonType: "decimal",
          minimum: NumberDecimal("0.00")
        },
        placedAt: { bsonType: "date" }
      }
    }
  };

  const stillInvalid = orders.countDocuments({
    dataset: tag,
    $nor: [validator]
  });
  print("Document sai schema còn lại: " + stillInvalid);
})();
~~~

**Kết quả mong đợi:** hai update đều thành công và số document sai schema còn lại là **0**. Sửa đủ trường trong một lần update vẫn hợp lệ dưới strict + error vì MongoDB đánh giá **document sau cập nhật**.

Trong ví dụ này chỉ có ba document. Một migration production nên chia batch, ghi số lượng trước/sau, dùng điều kiện nhận diện giá trị cần sửa, có chiến lược tiếp tục sau lỗi và được kiểm chứng trên dữ liệu sao chép hoặc môi trường staging trước.

## 7. Áp dụng validation vào collection hiện có bằng collMod

Với collection **đã tồn tại**, không cần tạo lại collection. Dùng **collMod**:

~~~javascript
db.getSiblingDB("mongo_validation_lab").runCommand({
  collMod: "lab_orders_legacy",
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["orderNo", "status", "amount"],
      properties: {
        orderNo: { bsonType: "string" },
        status: { enum: ["pending", "paid", "cancelled"] },
        amount: { bsonType: "decimal" }
      }
    }
  },
  validationLevel: "moderate",
  validationAction: "error"
});
~~~

Đây là **một validator minh họa ngắn hơn** validator của lab ở mục 6. Chạy lệnh này sẽ **thay thế** validator trên collection tương ứng. Chỉ làm khi bạn chủ đích muốn đổi quy tắc; nếu vừa thực hành mục 6, dùng lại validator đầy đủ để giữ cùng hợp đồng dữ liệu. Với migration thật, nên quản lý định nghĩa validator có phiên bản như mã nguồn thay vì sao chép thủ công nhiều biến thể.

Đọc cấu hình collection:

~~~javascript
db.getSiblingDB("mongo_validation_lab").getCollectionInfos({
  name: "lab_orders_legacy"
});
~~~

Thông tin trong **options** của collection cho biết validator, validationLevel và validationAction đang được cấu hình. Cần phân biệt **cấu hình đã được áp dụng** với **dữ liệu đã tuân thủ**: getCollectionInfos không thay thế truy vấn kiểm kê document sai.

### 7.1. Nhắc về additionalProperties

Trong JSON Schema, **additionalProperties: false** có thể giúp chặn field lạ, nhưng phải xét cả **_id** và các trường metadata được ứng dụng/driver bổ sung. Nếu không khai báo _id là property hợp lệ, một cấu hình quá chặt có thể từ chối document bình thường vì có _id. Ngoài ra, thay đổi schema của ứng dụng mà không thay validator có thể gây lỗi ghi đột ngột.

Ví dụ một schema chặt:

~~~javascript
{
  $jsonSchema: {
    bsonType: "object",
    required: ["orderNo", "status"],
    additionalProperties: false,
    properties: {
      _id: {},
      orderNo: { bsonType: "string" },
      status: { enum: ["pending", "paid", "cancelled"] }
    }
  }
}
~~~

Đây chỉ là ví dụ cho hai trường nghiệp vụ; không dùng nguyên mẫu để thay thế validator có thêm tenantId, amount, placedAt, schemaVersion hoặc các trường cần thiết của hệ thống thật.

### 7.2. bypassDocumentValidation

Một số thao tác ghi có thể sử dụng **bypassDocumentValidation** nếu người dùng/role có quyền tương ứng. Vì thế trong các mức thông thường, schema validation không thay thế phân quyền và quản trị tài khoản. Chỉ cấp quyền bypass cho tác vụ quản trị/migration có kiểm soát, ghi lại lý do và phạm vi sử dụng. Trên MongoDB 9.0 ở mức **constraint**, bypass bị chặn theo hợp đồng của mức này.

Không dùng bypass để làm cho dữ liệu sai biến mất khỏi báo cáo: bypass cho phép ghi một số dữ liệu không hợp lệ, còn dữ liệu đó vẫn phải được kiểm kê và xử lý.

## 8. Lộ trình triển khai trong hệ thống thật

Một hệ thống có collection đang được nhiều dịch vụ ghi thường cần triển khai theo giai đoạn:

### Giai đoạn 1 — Quan sát trước khi chặn

Định nghĩa schema mục tiêu, kiểm tra loại BSON đang có, đo số document sai và xác định hệ thống nào tạo ra. Có thể tạm dùng **strict + warn** để quan sát các thao tác insert/update tạo ra post-image không hợp lệ. Cần có quyền đọc server log và công cụ tổng hợp cảnh báo; số lượng cảnh báo không phải là số lượng document sai đang tồn tại.

Ở giai đoạn này, sửa code của các dịch vụ ghi, migration tool, job import và các client cũ. Nếu ứng dụng vẫn chèn amount dưới dạng String, chuyển ngay sang strict + error sẽ biến lỗi dữ liệu thành lỗi vận hành.

### Giai đoạn 2 — Chặn lỗi mới, cho phép sửa legacy

Sau khi các luồng ghi mới đã tương thích, **moderate + error** thường là giai đoạn chuyển tiếp hữu ích:

- Insert mới sai bị chặn.
- Document hiện đang hợp lệ không được làm sai thêm.
- Update document hiện đang sai vẫn có thể được xử lý để phục vụ hoạt động cũ và migration.

Nhưng cần quản lý một hàng đợi migration vì moderate **không thúc đẩy** legacy tự trở nên hợp lệ.

### Giai đoạn 3 — Làm sạch dữ liệu cũ

Truy vấn document sai bằng **$nor** và schema mục tiêu, chia theo nhóm nguyên nhân, sửa có điều kiện và đọc lại kết quả. Chú ý các tình huống:

| Loại vi phạm | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| Thiếu trường bắt buộc | Thiếu status | Suy ra từ nguồn nghiệp vụ đáng tin; không tự điền giá trị tùy tiện |
| Sai kiểu dữ liệu | amount lưu String | Parse rõ định dạng, lưu Decimal128, xử lý chuỗi không chuyển được |
| Giá trị ngoài tập hợp | status = old_state | Lập bảng mapping có kiểm soát, hoặc quản lý version schema |
| Ngày không đúng kiểu | placedAt là String | Xác định timezone và định dạng; không đoán ngày không rõ |
| Document mang hình dạng từ phiên bản cũ | Thiếu nhiều trường mới | Migration nhiều bước hoặc schema chuyển tiếp với rule cho từng phiên bản |
| Document bị trùng khóa nghiệp vụ | Hai orderNo cùng tenant | Phân tích và xử lý trước khi tạo unique index, không xóa mù |

Với hàng triệu document, một lệnh updateMany trên toàn collection có thể gây áp lực ghi, replication lag và thay đổi lớn trong khoảng thời gian ngắn. Nên thiết kế batch, giới hạn lưu lượng, theo dõi lỗi, có checkpoint và đảm bảo chạy lại an toàn.

### Giai đoạn 4 — Enforcement đầy đủ

Khi ứng dụng và dữ liệu cũ đã tương thích, chuyển sang **strict + error** hoặc **errorAndLog** trên bản hỗ trợ. Ở đây strict ngăn insert/update sai, nhưng **không tự chứng minh toàn bộ document vốn đã hợp lệ** vì strict không quét ngược. Do đó vẫn phải chạy truy vấn kiểm kê và theo dõi số document invalid sau chuyển.

Nếu MongoDB 9.0+ và nghiệp vụ cần ràng buộc **toàn collection** bằng validation mức cao hơn, có thể xem xét constraint sau khi đánh giá chi phí quét và quy trình chuẩn bị.

### Giai đoạn 5 — Duy trì qua các phiên bản schema

Mỗi lần tăng độ chặt của validator (ví dụ thêm required field), một document trước đây hợp lệ có thể trở thành invalid. Cần chuẩn bị:

- Triển khai code có thể đọc cả dữ liệu cũ và mới trong giai đoạn chuyển tiếp.
- Quy tắc mặc định hoặc migration có cơ sở nghiệp vụ.
- Phiên bản schema khi một collection chủ động chứa nhiều biến thể.
- Lịch chuyển đổi validator tương ứng với thời điểm tất cả writer đã được nâng cấp.
- Khả năng quan sát document invalid theo từng ngày, tenant, phiên bản ứng dụng và loại lỗi.

Không nên đồng thời yêu cầu field mới, ngắt hỗ trợ dữ liệu cũ và tăng strict enforcement trong một lần triển khai không có cơ chế chuyển tiếp.

## 9. constraint nâng cao trên MongoDB 9.0+

Nếu môi trường chạy MongoDB 9.0 trở lên, sau khi collection đã về **strict + error** và dữ liệu đều hợp lệ, quy trình nâng mức bảo đảm có thể như sau:

~~~javascript
const lab = db.getSiblingDB("mongo_validation_lab");

// 1. Định nghĩa validator phải đã được cấu hình đúng ở strict.
printjson(lab.runCommand({
  collMod: "lab_orders_legacy",
  validationLevel: "strict",
  validationAction: "error"
}));

// 2. Chuẩn bị nâng cấp: chặn bypass và ngăn đổi validator.
printjson(lab.runCommand({
  collMod: "lab_orders_legacy",
  prepareConstraintValidationLevel: true
}));

// 3. MongoDB quét collection khi nâng cấp; fail nếu còn invalid.
printjson(lab.runCommand({
  collMod: "lab_orders_legacy",
  validationLevel: "constraint",
  validationAction: "error"
}));
~~~

**Đoạn này là phần mở rộng tùy chọn, không nằm trong luồng lab 6**. Không chạy trên MongoDB trước 9.0. Trước khi nâng cấp một collection thật, đánh giá tác động quét toàn collection, quyền quản trị, các writer và kế hoạch rollback. Khi đã ở constraint, phải hạ về strict trước khi cần thay validator; không thêm validator mới vào cùng lệnh nâng cấp constraint.

## 10. Phân biệt validator và các cơ chế toàn vẹn khác

Schema validation giải quyết **hình dạng và điều kiện của document**, nhưng không thay thế các phần sau:

| Nhu cầu | Cơ chế thích hợp | Vì sao validation chưa đủ? |
| --- | --- | --- |
| Không trùng orderNo trong tenant | Unique compound index | Validator không tự kiểm tra tính duy nhất giữa nhiều document |
| customerId trỏ tới customer đang tồn tại | Logic ứng dụng/transaction phù hợp | Không có ràng buộc foreign key tự động giữa collection |
| Không cho người dùng xem đơn khác tenant | Xác thực, phân quyền, filter theo tenant | Validator không biết ai có quyền đọc |
| Bảo vệ update đồng thời | Filter theo trạng thái/phiên bản, giao dịch | Một document hợp schema vẫn có thể bị ghi đè logic |
| Đảm bảo số tiền tính đúng theo đơn | Validation nghiệp vụ, tính toán/kiểm soát ở server | Kiểu Decimal128 đúng chưa chứng minh công thức tổng đúng |
| Ghi Order và AuditEvent cùng thành công | Multi-document transaction/outbox theo yêu cầu | Validation mỗi document không tạo tính nguyên tử giữa collection |
| Tìm nhanh theo customerId, placedAt | Compound index và tối ưu truy vấn | Validator không thay thế index cho đọc |

Ví dụ dù validator chấp nhận status = paid, một yêu cầu chuyển thẳng từ cancelled sang paid có thể vẫn bị **logic nghiệp vụ** cấm. Cả hai document trước và sau đều hợp schema, nhưng chuyển trạng thái chưa chắc hợp lệ.

## 11. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân điển hình | Cách điều tra |
| --- | --- | --- |
| Insert bị lỗi 121 | Document không thỏa validator dưới action error | Xem thông báo lỗi, schema hiện hành, kiểu BSON và required fields |
| Update chỉ sửa note cũng lỗi 121 | strict kiểm tra toàn post-image của document legacy vốn sai | Tìm lỗi cũ; sửa đủ lỗi trong update hoặc dùng lộ trình migration |
| moderate + error vẫn cho update document invalid | moderate không kiểm tra update của document đang invalid | Đó là hành vi thiết kế; cần migration và kiểm kê riêng |
| warn không làm client thấy lỗi | warn cho ghi tiếp tục và báo qua server log | Quan sát mongod log/monitoring; truy vấn invalid documents |
| collMod strict thành công nhưng còn dữ liệu sai | strict không kiểm tra ngược toàn collection | Dùng $nor + validator để đếm document invalid |
| Lệnh sửa dữ liệu thất bại dù đã đổi validationLevel off | Có ràng buộc khác như unique index, immutable _id hoặc quyền | Đọc mã lỗi thực tế; không quy mọi lỗi về validator |
| BSON type không khớp | String/Double/Int64 khác Decimal128 | Dùng $type và chuyển đổi dữ liệu có chủ đích |
| Constraint upgrade không thành công | Còn document invalid hoặc chưa chuẩn bị đúng quy trình | Kiểm kê invalid, xác nhận phiên bản 9.0+ và các bước prepare |
| Đổi validator làm ứng dụng cũ bắt đầu lỗi | Nhiều writer chưa tương thích schema mới | Inventory các luồng ghi và triển khai có giai đoạn |
| Tạo validationAction errorAndLog bị từ chối | MongoDB chưa hỗ trợ hoặc cấu hình không phù hợp | Kiểm tra db.version() và khả năng của server |
| TTL/unique index vẫn tác động dù validationLevel off | Đây là ràng buộc độc lập với schema validation | Kiểm tra getIndexes và các quy tắc riêng của collection |

### 11.1. Quan sát kiểu BSON

Khi gặp câu hỏi “trường amount trông như số nhưng sao vẫn bị chặn?”, dùng aggregation:

~~~javascript
db.getSiblingDB("mongo_validation_lab")
  .getCollection("lab_orders_legacy")
  .aggregate([
    { $match: { dataset: "schema-legacy-v1" } },
    {
      $project: {
        _id: 1,
        amountType: { $type: "$amount" },
        statusType: { $type: "$status" },
        placedAtType: { $type: "$placedAt" }
      }
    }
  ]).toArray();
~~~

MongoDB phân biệt **decimal**, **string**, **int**, **long**, **double**, **date**. Định nghĩa **bsonType: "decimal"** không chấp nhận một chuỗi chỉ vì nó chứa chữ số. Sự nhất quán kiểu rất quan trọng khi dữ liệu được ghi từ nhiều driver/ngôn ngữ.

### 11.2. Khi nào cần kiểm tra quyền bypass?

Nếu dữ liệu sai vẫn được insert dù đã bật strict + error, hãy xác nhận:

1. Ứng dụng thực sự ghi vào **đúng database và collection** đang có validator.
2. Không có thao tác hoặc tài khoản đặc quyền sử dụng **bypassDocumentValidation**.
3. getCollectionInfos cho thấy validationLevel/action hiện tại đúng như dự kiến.
4. Những document đó là dữ liệu đã có từ trước hay vừa được ghi mới.
5. Phiên bản schema đang kiểm tra có đúng kiểu dữ liệu và thuộc tính required không.

Không kết luận có lỗi MongoDB chỉ từ việc đọc thấy document sai; strict không quét và sửa document legacy.

## 12. Bài tập thực hành

**Bài 1 — Ma trận chính sách.** Dựa vào ba document của lab, dự đoán thao tác insert thiếu status, update current-valid thành amount dạng String và update ghi chú của old-missing-status sẽ được chấp nhận hay từ chối ở từng tổ hợp strict/error, strict/warn, moderate/error, moderate/warn và off/error. Giải thích theo thứ tự: **có bị kiểm tra hay không**, rồi **nếu sai thì xử lý thế nào**.

**Bài 2 — Migration từ schema cũ.** Tạo thêm một document legacy có placedAt là String ISO, sau đó tìm bằng $nor + $jsonSchema. Hãy lập quy tắc chuyển String sang BSON Date có timezone rõ ràng; xử lý trường hợp chuỗi trống, không thể parse hoặc không biết timezone. Chỉ cập nhật khi có dữ liệu hợp lệ.

**Bài 3 — Cập nhật từng phần.** Ở strict + error, vì sao update chỉ sửa migrationNote trên document old-missing-status ban đầu thất bại? Viết một update sửa status và migrationNote cùng lúc. Nếu được, quan sát liệu post-image đã thỏa validator.

**Bài 4 — Chuyển đổi theo giai đoạn.** Một collection có 10 triệu document; 2% thiếu status; mỗi ngày có 100.000 đơn mới. Viết kế hoạch chuyển từ không có validation sang strict + error, bao gồm số liệu cần theo dõi, kiểm kê, sửa các writer và điều kiện kết thúc migration.

**Bài 5 — Phiên bản mới.** Schema mới muốn thêm trường currency bắt buộc. Hãy phân tích vì sao áp dụng strict + error ngay có thể làm update legacy lỗi. So sánh hai chiến lược: hỗ trợ đồng thời schema cũ/mới trong giai đoạn chuyển tiếp, hoặc bổ sung currency vào toàn bộ document trước khi tăng required.

**Bài 6 — Lưu log và enforcement.** Phân biệt mục tiêu dùng warn với errorAndLog. Nếu ứng dụng báo ghi thành công nhưng monitoring phát hiện cảnh báo schema, khả năng validationAction nào đang được dùng? Cần kiểm tra thêm gì trước khi bật chặn ghi?

**Bài 7 — Constraint (MongoDB 9.0+).** Giải thích vì sao nâng cấp strict sang constraint phải quét toàn collection, vì sao không được dùng warn trong constraint và vì sao cần chuẩn bị trước khi nâng cấp. Nêu tác động có thể gặp nếu collection rất lớn và đang có tải ghi.

## 13. Tài liệu tham khảo

- MongoDB Manual — [Specify Validation Level for Existing Documents](https://www.mongodb.com/docs/manual/core/schema-validation/specify-validation-level/).
- MongoDB Manual — [Choose How to Handle Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/handle-invalid-documents/).
- MongoDB Manual — [Query for and Modify Valid or Invalid Documents](https://www.mongodb.com/docs/manual/core/schema-validation/use-json-schema-query-conditions/).
- MongoDB Manual — [collMod command](https://www.mongodb.com/docs/manual/reference/command/collmod/).

**Kết luận áp dụng:** **validationLevel** quyết định *khi nào validator được chạy*; **validationAction** quyết định *hệ quả của một lần kiểm tra không đạt*. Document cũ không tự được sửa khi thêm validator ở strict hoặc moderate. Với collection đang có dữ liệu, nên kiểm kê lỗi và các writer, làm sạch dữ liệu theo quy tắc đáng tin cậy, rồi tăng enforcement có kiểm soát. Chỉ khi quy trình ghi mới và dữ liệu tồn tại đều đáp ứng hợp đồng schema, việc bật ràng buộc chặt mới mang lại lợi ích mà không phá vỡ luồng xử lý cần thiết.
