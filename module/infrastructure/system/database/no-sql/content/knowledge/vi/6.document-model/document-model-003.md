# Biểu diễn thực thể có thuộc tính thay đổi và các phiên bản tài liệu

Một đặc điểm quan trọng của **mô hình tài liệu** (*document model*) trong NoSQL là khả năng biểu diễn thực thể có thuộc tính không hoàn toàn giống nhau. Cùng thuộc tập sản phẩm, điện thoại có dung lượng RAM và kích thước màn hình; áo có kích cỡ và chất liệu; một sản phẩm có thể bổ sung thông số mới sau khi hệ thống đã vận hành hàng năm. Khi lưu dưới dạng tài liệu, ta có thể tổ chức các thuộc tính này thành trường, đối tượng lồng nhau hoặc mảng mà không nhất thiết yêu cầu mọi tài liệu có cùng bộ trường cố định.

Nhưng có hai bài toán cần tách biệt:

1. **Thuộc tính của thực thể thay đổi:** những thực thể cùng loại có thuộc tính tùy chọn, các nhóm thực thể có trường chuyên biệt, hoặc quy tắc cấu trúc dữ liệu thay đổi theo thời gian.
2. **Tài liệu có phiên bản:** ứng dụng cần biết tài liệu tuân theo phiên bản cấu trúc nào, đã trải qua bao nhiêu lần cập nhật, hoặc có cần giữ những trạng thái cũ để tra cứu và kiểm toán.

Hai bài toán thường đi cùng nhau, nhưng **“schema linh hoạt” không có nghĩa “không có schema”**, và **“tài liệu có version” có thể mang nhiều ý nghĩa khác nhau**. Nếu không phân biệt, hệ thống dễ gặp lỗi đọc tài liệu cũ, mất cập nhật khi có nhiều yêu cầu đồng thời, hoặc lưu lịch sử mà không thể tái dựng trạng thái mong muốn.

## 1. Tài liệu biểu diễn thực thể như thế nào?

Một **tài liệu** (*document*) thường chứa cặp tên trường–giá trị, có thể có đối tượng lồng nhau và mảng. JSON là cách hiển thị phổ biến; một số DBMS như MongoDB lưu tài liệu bằng **BSON**, với những kiểu dữ liệu và quy tắc riêng.

Ví dụ một điện thoại trong tập sản phẩm:

~~~json
{
  "_id": "P-1001",
  "type": "phone",
  "name": "Điện thoại A",
  "status": "ACTIVE",
  "price": {
    "amount": 8500000,
    "currency": "VND"
  },
  "attributes": {
    "ramGb": 8,
    "storageGb": 256,
    "screenInches": 6.5,
    "supportsEsim": true
  }
}
~~~

Một sản phẩm áo cùng nằm trong collection `products` nhưng có bộ thuộc tính khác:

~~~json
{
  "_id": "P-2001",
  "type": "shirt",
  "name": "Áo sơ mi B",
  "status": "ACTIVE",
  "price": {
    "amount": 320000,
    "currency": "VND"
  },
  "attributes": {
    "size": "M",
    "material": "cotton",
    "color": "navy",
    "careInstructions": ["wash-cold", "do-not-bleach"]
  }
}
~~~

Hai tài liệu có **phần lõi chung**: `_id`, `type`, `name`, `status`, `price`. Phần `attributes` thể hiện đặc điểm riêng của từng loại sản phẩm. Với cách biểu diễn này, ứng dụng có thể đọc toàn bộ thông tin thường dùng của một sản phẩm bằng một lần truy xuất theo ID.

### “Thực thể” không đồng nghĩa với “một tài liệu” trong mọi tình huống

*Thực thể* là khái niệm nghiệp vụ có danh tính tương đối ổn định: khách hàng, sản phẩm, hợp đồng, đơn hàng. *Tài liệu* là đơn vị biểu diễn và lưu trữ mà DBMS cung cấp. Thường một thực thể tương ứng một tài liệu, nhưng không bắt buộc:

- Một đơn hàng có thể chứa mảng dòng hàng được **nhúng** trong cùng tài liệu.
- Một khách hàng có thể có tài liệu hồ sơ, một tập địa chỉ và nhiều tài liệu giao dịch liên kết bằng ID.
- Một thực thể có thể có **tài liệu trạng thái hiện hành** và nhiều tài liệu **lịch sử phiên bản**.
- Một tài liệu báo cáo có thể chứa thông tin tổng hợp của nhiều thực thể và là **dữ liệu dẫn xuất**, không phải bản ghi nguồn có thẩm quyền.

Vì vậy, trước khi quyết định nhúng hay tách, cần xác định **đơn vị đọc/ghi, ranh giới cập nhật nguyên tử, tần suất thay đổi và kích thước tài liệu**.

## 2. Ba dạng thay đổi thuộc tính thường gặp

Không phải mọi thay đổi thuộc tính đều có cùng ý nghĩa. Có thể chia thành ba tình huống:

| Tình huống | Ví dụ | Bài toán thiết kế |
| --- | --- | --- |
| **Khác nhau giữa các thực thể** | Điện thoại có RAM, áo có kích cỡ | Biểu diễn các nhóm thực thể không có cùng tất cả trường |
| **Thuộc tính xuất hiện hoặc biến mất theo vòng đời** | Sản phẩm mới chưa có đánh giá; sau khi bán có `averageRating` | Phân biệt trường chưa có, chưa áp dụng, chưa biết và giá trị thực |
| **Cấu trúc/ý nghĩa trường đổi theo phiên bản hệ thống** | `priceVnd` đổi thành `price.amount` + `price.currency` | Đọc tài liệu cũ, chuyển đổi dữ liệu, duy trì tương thích |

Ví dụ trong cùng loại điện thoại:

~~~json
{
  "_id": "P-1002",
  "type": "phone",
  "name": "Điện thoại C",
  "attributes": {
    "ramGb": 12,
    "storageGb": 512
  }
}
~~~

Tài liệu này **không có `supportsEsim`**. Không nên tự kết luận thiết bị không hỗ trợ eSIM; có thể thông tin chưa được nhập, thuộc tính chưa áp dụng hoặc phiên bản dữ liệu cũ chưa có trường đó. Cách xử lý đúng phụ thuộc quy ước nghiệp vụ và schema.

Một thay đổi khác là sản phẩm từng được biểu diễn bằng:

~~~json
{
  "_id": "P-1001",
  "name": "Điện thoại A",
  "priceVnd": 8500000
}
~~~

Sau khi mở rộng sang nhiều đơn vị tiền tệ, ứng dụng chuyển sang:

~~~json
{
  "_id": "P-1001",
  "name": "Điện thoại A",
  "price": {
    "amount": 8500000,
    "currency": "VND"
  }
}
~~~

Đây là **thay đổi schema**. Nếu ứng dụng mới chỉ đọc `price.amount` nhưng trong kho vẫn còn tài liệu chỉ có `priceVnd`, kết quả có thể bị thiếu hoặc gây lỗi. Schema linh hoạt cho phép hai biểu diễn cùng tồn tại ở mức lưu trữ; ứng dụng vẫn phải xử lý được sự khác biệt đó.

## 3. Các cách biểu diễn thực thể có thuộc tính không đồng nhất

### 3.1. Đưa mọi thuộc tính lên cùng cấp

Ví dụ:

~~~json
{
  "_id": "P-1001",
  "type": "phone",
  "name": "Điện thoại A",
  "ramGb": 8,
  "storageGb": 256,
  "screenInches": 6.5
}
~~~

Ưu điểm là tài liệu ngắn, cú pháp truy cập trực tiếp: `ramGb`, `storageGb`. Hạn chế xuất hiện khi hệ thống có hàng trăm nhóm sản phẩm: phần lõi và thuộc tính riêng trộn vào nhau, trùng tên trường có thể mang ý nghĩa khác nhau, khó xác định trường nào thuộc loại sản phẩm nào.

Cách này phù hợp khi số loại thực thể ít, số trường riêng nhỏ và quy ước đặt tên rõ ràng. Nó không tự sai; điều quan trọng là ứng dụng phải quản lý các trường và kiểu của chúng.

### 3.2. Tách phần lõi và vùng thuộc tính mở rộng

Ví dụ:

~~~json
{
  "_id": "P-1001",
  "type": "phone",
  "name": "Điện thoại A",
  "status": "ACTIVE",
  "attributes": {
    "ramGb": 8,
    "storageGb": 256,
    "screenInches": 6.5
  }
}
~~~

Phần lõi giúp các chức năng chung (danh sách sản phẩm, trạng thái, tên, chủ sở hữu) truy cập cùng một cấu trúc. Vùng `attributes` chứa những trường phụ thuộc `type`.

Ưu điểm:

- Ranh giới giữa **thuộc tính chung** và **thuộc tính chuyên biệt** rõ ràng.
- Có thể bổ sung thuộc tính mới mà không cần thêm trường vào mọi tài liệu.
- Dễ áp dụng quy tắc validation theo `type` trong ứng dụng.

Đánh đổi:

- Không thể giả định mọi tài liệu có mọi đường dẫn `attributes.*`.
- Những truy vấn lọc/sắp xếp theo trường động phải tính đến index và kiểu dữ liệu.
- Các nhóm thực thể khác nhau có thể cần schema validation khác nhau, khiến logic ứng dụng phức tạp hơn.

### 3.3. Danh sách thuộc tính dạng tên–giá trị

Một số hệ thống quản lý thông số do người dùng định nghĩa có thể biểu diễn:

~~~json
{
  "_id": "P-1001",
  "type": "phone",
  "attributes": [
    {
      "code": "ram",
      "value": 8,
      "unit": "GB"
    },
    {
      "code": "screen",
      "value": 6.5,
      "unit": "inch"
    }
  ]
}
~~~

Cách này cho phép mỗi thuộc tính mang metadata như `code`, `unit`, nguồn đo, thời điểm ghi hoặc nhãn hiển thị; nhưng truy vấn “RAM từ 8 GB trở lên” phức tạp hơn so với đường dẫn trực tiếp `attributes.ramGb`. Nếu lưu tất cả giá trị dưới dạng string, ví dụ `"8"` và `"16"`, so sánh số học và sắp xếp sẽ sai về ngữ nghĩa nếu không chuyển kiểu.

Khi lọc theo nhiều thuộc tính trong một mảng đối tượng, còn phải đảm bảo các điều kiện cùng khớp **một phần tử** nếu đó là yêu cầu nghiệp vụ. Ví dụ trong MongoDB, toán tử `$elemMatch` giúp biểu diễn điều kiện cùng phần tử; cú pháp và khả năng index cần được kiểm tra theo sản phẩm.

### 3.4. Tách loại tài liệu hoặc collection theo nhóm

Một phương án khác là lưu `phones`, `shirts` ở các collection khác nhau, hoặc có tập tài liệu mở rộng riêng gắn với ID sản phẩm:

~~~text
products
  P-1001 → {name, status, price, type:"phone"}
  P-2001 → {name, status, price, type:"shirt"}

phone_specs
  P-1001 → {ramGb, storageGb, screenInches}

shirt_specs
  P-2001 → {size, material, color}
~~~

Phương án này có thể hữu ích khi mỗi nhóm có kiểu truy vấn, index, vòng đời hoặc quyền truy cập khác nhau đáng kể. Đổi lại, truy vấn chi tiết sản phẩm có thể cần ghép dữ liệu từ nhiều nơi hoặc thêm request. **Mô hình tài liệu không bắt buộc mọi thứ phải được nhúng vào một tài liệu lớn.**

### Chọn cách biểu diễn bằng mẫu truy cập

| Mẫu truy cập | Phương án đáng khảo sát |
| --- | --- |
| Đọc hồ sơ và các thuộc tính riêng cùng nhau | Tài liệu có lõi chung và `attributes` lồng nhau |
| Thuộc tính có metadata riêng, thay đổi tùy người dùng | Mảng thuộc tính hoặc bảng/cấu trúc định nghĩa thuộc tính |
| Lọc liên tục trên RAM, bộ nhớ, kích thước | Trường có kiểu rõ và index theo đường dẫn truy vấn |
| Mỗi nhóm sản phẩm có quy tắc cập nhật hoàn toàn khác nhau | Collection chuyên biệt hoặc tài liệu mở rộng riêng |
| Một tập thuộc tính tăng không giới hạn, cập nhật rất thường xuyên | Cân nhắc tách để tránh tài liệu quá lớn và tranh chấp ghi |

Không thể chọn chỉ từ chữ “linh hoạt”. Cần biết dữ liệu sẽ **đọc theo ID, lọc theo thuộc tính, cập nhật phần nào, và có bao nhiêu kiểu khác nhau**.

## 4. Phân biệt thiếu trường, null, mặc định và giá trị không hợp lệ

Trong dữ liệu có thuộc tính tùy chọn, bốn tình trạng sau khác nhau:

~~~json
{"_id":"A", "attributes":{"warrantyMonths":12}}
{"_id":"B", "attributes":{"warrantyMonths":null}}
{"_id":"C", "attributes":{}}
{"_id":"D", "attributes":{"warrantyMonths":"unknown"}}
~~~

- **A:** có giá trị số 12.
- **B:** có trường nhưng giá trị `null`; phải quy định `null` nghĩa là chưa biết, không áp dụng hay xóa giá trị.
- **C:** thiếu trường; có thể do chưa nhập, dữ liệu thuộc phiên bản cũ hoặc không áp dụng.
- **D:** giá trị string `"unknown"`; khác kiểu số nếu schema kỳ vọng số tháng bảo hành.

Không nên nhập nhằng giữa `null`, thiếu trường, `0`, chuỗi rỗng và `false`. Chẳng hạn:

- Số tháng bảo hành bằng `0` có thể nghĩa là không bảo hành.
- Không có trường bảo hành có thể nghĩa là chưa được xác định.
- Giá trị `null` có thể được dùng để biểu diễn “không áp dụng”, nếu đó là quy ước đã thống nhất.

**Giá trị mặc định** cũng phải rõ nguồn gốc: mặc định ở giao diện, ở bộ đọc tài liệu, ở tầng nghiệp vụ hay được ghi thật vào kho? Nếu mặc định của hệ thống sau này đổi từ 12 tháng sang 6 tháng, những tài liệu không có trường bảo hành có được áp dụng mặc định mới không? Đây là quyết định nghiệp vụ, không chỉ là vấn đề cú pháp.

### Lưu ý khi truy vấn trường không tồn tại

Ví dụ với MongoDB:

~~~javascript
// Tìm tài liệu có đường dẫn thuộc tính.
db.products.find({
  "attributes.warrantyMonths": { $exists: true }
});

// Tìm tài liệu có giá trị là số.
db.products.find({
  "attributes.warrantyMonths": { $type: "number" }
});
~~~

Hai truy vấn phục vụ hai mục đích khác nhau: `$exists` kiểm tra sự có mặt của trường (kể cả khi giá trị là `null`), còn `$type` kiểm tra kiểu theo quy tắc MongoDB. Truy vấn dùng `{ field: null }` có ngữ nghĩa khớp cả trường null và trường thiếu trong nhiều trường hợp; cần chủ động thiết kế để tránh báo cáo sai.

## 5. Schema linh hoạt vẫn cần hợp đồng cấu trúc

Một DBMS tài liệu có thể cho phép tài liệu không có bộ cột thống nhất. Điều đó **không miễn trừ việc xác định schema** ở tầng nghiệp vụ.

Hợp đồng cho loại `phone` có thể nói:

~~~yaml
entityType: phone
requiredCoreFields:
  - _id
  - type
  - name
  - schemaVersion
  - revision
attributeRules:
  ramGb:
    type: integer
    min: 1
    required: true
  storageGb:
    type: integer
    min: 1
    required: true
  supportsEsim:
    type: boolean
    required: false
~~~

Đây là ví dụ **đặc tả minh họa**, không phải cấu hình mà MongoDB tự đọc. Muốn áp dụng, ứng dụng phải có cơ chế validation phù hợp hoặc chuyển quy tắc sang validator mà DBMS hỗ trợ.

Có thể kiểm tra ở nhiều tầng:

1. **Tầng giao diện:** giúp người nhập biết trường hợp lệ và thông báo lỗi sớm.
2. **API/application:** kiểm tra quy tắc nghiệp vụ, giá trị có điều kiện theo `type`, phiên bản và quyền cập nhật.
3. **DBMS:** sử dụng validation, ràng buộc hoặc kiểm tra kiểu nếu sản phẩm hỗ trợ; bảo vệ dữ liệu khỏi những client khác ghi trực tiếp.
4. **Luồng nhập dữ liệu:** xác nhận kiểu dữ liệu, mã hóa, quy ước timezone/đơn vị và quy tắc mapping.

Đừng chỉ kiểm tra ở giao diện vì dữ liệu còn có thể đến từ batch import, các dịch vụ khác hoặc script quản trị.

### Schema theo nhóm thực thể

Một collection hỗn hợp thường cần các quy tắc có điều kiện:

~~~text
type = "phone" → attributes.ramGb và storageGb là số nguyên dương
type = "shirt" → attributes.size thuộc tập S/M/L/XL
type = "book"  → attributes.isbn theo quy tắc mã sách
~~~

Chỉ kiểm tra “`attributes` là object” chưa đủ để bảo đảm nghiệp vụ. Ngược lại, ép mọi loại sản phẩm phải có `ramGb` cũng không hợp lý. Giải pháp là có **phần lõi chung** và **schema đặc thù theo loại**, với quyết định rõ về trường không biết trước.

Cho phép tự do đặt mọi key trong `attributes` còn đặt ra vấn đề tên trường không hợp lệ, trùng nghĩa, sai chính tả (`storageGb` và `storageGB`), dữ liệu tùy ý quá lớn và chỉ mục khó kiểm soát. Một hệ thống mở rộng thuộc tính có thể cần **bảng từ điển thuộc tính** (*attribute registry*): mã, kiểu, đơn vị, nhóm áp dụng, khả năng tìm kiếm, quyền thay đổi và phiên bản định nghĩa.

## 6. “Phiên bản tài liệu” có ít nhất bốn nghĩa

Tên trường `version` một mình thường quá mơ hồ. Trong thiết kế, nên tách:

| Loại phiên bản | Trả lời câu hỏi | Ví dụ trường |
| --- | --- | --- |
| **Phiên bản schema** | Tài liệu tuân theo cấu trúc/ý nghĩa dữ liệu nào? | `schemaVersion: 2` |
| **Phiên bản sửa đổi kỹ thuật** | Tài liệu đã cập nhật bao nhiêu lần để phát hiện ghi đè đồng thời? | `revision: 7` |
| **Phiên bản nghiệp vụ** | Sản phẩm/hợp đồng/chính sách đang ở lần phát hành nào? | `businessVersion: "2026.2"` |
| **Phiên bản lịch sử** | Trạng thái tài liệu tại một thời điểm trước đó là gì? | Snapshot có `entityId`, `revision`, `recordedAt` |

Ví dụ một tài liệu có cả ba metadata đầu:

~~~json
{
  "_id": "P-1001",
  "type": "phone",
  "schemaVersion": 2,
  "revision": 7,
  "businessVersion": "2026.2",
  "name": "Điện thoại A",
  "attributes": {
    "ramGb": 8,
    "storageGb": 256
  },
  "createdAt": "2026-09-01T08:00:00Z",
  "updatedAt": "2026-10-12T09:15:00Z"
}
~~~

- `schemaVersion = 2` nói cách hiểu cấu trúc tài liệu. Nhiều tài liệu có thể cùng schema version dù cập nhật ở những thời điểm khác nhau.
- `revision = 7` nói lần sửa đổi logic của **tài liệu cụ thể**. Revision thay đổi khi có cập nhật cần được theo dõi, nhưng tăng bao nhiêu và khi nào tăng là hợp đồng của ứng dụng.
- `businessVersion = "2026.2"` là phiên bản sản phẩm theo nghiệp vụ. Nó có thể không đổi dù giá hoặc tồn kho thay đổi, và có thể cần một thực thể độc lập nếu các phiên bản sản phẩm được bán cùng lúc.

**Không đồng nhất `schemaVersion` với `revision`.** Một schema version có thể được dùng cho hàng triệu document; một document revision có thể tăng hàng trăm lần mà cấu trúc vẫn giữ nguyên.

## 7. Phiên bản schema: hỗ trợ tài liệu cũ và tài liệu mới cùng tồn tại

Giả sử lần đầu ứng dụng lưu giá như sau:

~~~json
{
  "_id": "P-1001",
  "schemaVersion": 1,
  "type": "phone",
  "name": "Điện thoại A",
  "priceVnd": 8500000,
  "specifications": {
    "ramGb": 8
  }
}
~~~

Phiên bản 2 hỗ trợ nhiều loại tiền tệ và tên trường nhất quán:

~~~json
{
  "_id": "P-1001",
  "schemaVersion": 2,
  "type": "phone",
  "name": "Điện thoại A",
  "price": {
    "amount": 8500000,
    "currency": "VND"
  },
  "attributes": {
    "ramGb": 8
  }
}
~~~

Một DBMS tài liệu có thể lưu cả hai mà không cần thay bảng theo nghĩa truyền thống. Nhưng **chương trình đọc** phải biết xử lý chúng:

~~~text
                Tài liệu từ DBMS
                        │
                schemaVersion?
                 /          \
                1            2
                │            │
        Chuyển sang        Kiểm tra
        mô hình hiện tại    mô hình hiện tại
                │            │
                └─────┬──────┘
                      ▼
          Product trong ứng dụng
          có cùng cấu trúc đầu ra
~~~

### Đọc phiên bản cũ bằng bộ chuyển đổi (*upcaster*)

Một ví dụ JavaScript mang tính minh họa:

~~~javascript
function toCurrentProduct(doc) {
  switch (doc.schemaVersion ?? 1) {
    case 1:
      return {
        id: doc._id,
        type: doc.type,
        name: doc.name,
        price: {
          amount: doc.priceVnd,
          currency: "VND"
        },
        attributes: doc.specifications ?? {},
        schemaVersion: 2,
        revision: doc.revision ?? 1
      };

    case 2:
      return {
        id: doc._id,
        type: doc.type,
        name: doc.name,
        price: doc.price,
        attributes: doc.attributes ?? {},
        schemaVersion: 2,
        revision: doc.revision ?? 1
      };

    default:
      throw new Error("Unsupported product schema version");
  }
}
~~~

Hàm trên tạo **mô hình đọc thống nhất trong bộ nhớ**, không tự thay đổi tài liệu lưu trong DBMS. Quy ước “thiếu `schemaVersion` thì coi là v1” chỉ đúng nếu ứng dụng biết chắc tài liệu cũ không có trường này. Nếu một tài liệu thiếu field vì dữ liệu lỗi, việc tự gán version 1 có thể che giấu lỗi.

Với giá trị tiền, định dạng `amount + currency` vẫn cần quy tắc về đơn vị nhỏ nhất, làm tròn và loại số để tránh sai khác; chuyển cấu trúc không đồng nghĩa đã giải quyết mọi ràng buộc nghiệp vụ.

### Những loại thay đổi schema khác nhau

| Thay đổi | Ví dụ | Điều cần cân nhắc |
| --- | --- | --- |
| Thêm trường tùy chọn | `supportsEsim` | Phân biệt thiếu trường với false |
| Thêm trường bắt buộc | `currency` | Cách lấp dữ liệu cũ và default hợp lệ |
| Đổi tên trường | `specifications` → `attributes` | Trình đọc/migration hỗ trợ cả hai tên trong giai đoạn chuyển |
| Đổi kiểu dữ liệu | `price: "8500000"` → số | Dữ liệu sai kiểu và truy vấn/index hiện tại |
| Tách trường | `priceVnd` → `price.amount` + `price.currency` | Chuyển ngữ nghĩa, không chỉ đổi tên |
| Gộp trường | `firstName` và `lastName` → `displayName` | Có thể mất khả năng khôi phục hai phần ban đầu |
| Đổi ý nghĩa | `discount: 10` từ phần trăm sang số tiền | Nguy hiểm vì cùng tên/kiểu nhưng khác ngữ nghĩa |
| Đổi cấu trúc nhúng/tham chiếu | `supplier` nhúng → `supplierId` | Cần truy cập hoặc join/lookup và xử lý nhất quán |

Một thay đổi schema được coi là **tương thích ngược** hay không phụ thuộc cả *reader* và *writer*. Thêm trường tùy chọn có thể an toàn với reader bỏ qua trường lạ, nhưng không an toàn nếu reader dùng cơ chế validate nghiêm và từ chối mọi thuộc tính không biết.

## 8. Lựa chọn chiến lược tiến hóa schema

Có nhiều chiến lược để ứng dụng mới và dữ liệu cũ cùng hoạt động.

### 8.1. Chỉ đọc và chuyển đổi khi cần (*lazy migration*)

Giữ dữ liệu cũ trong DBMS, khi đọc thì chuyển sang cấu trúc ứng dụng hiện tại. Nếu có cập nhật, ứng dụng có thể ghi tài liệu theo schema mới.

**Ưu điểm:** không phải chuyển toàn bộ dữ liệu ngay; phù hợp khi dữ liệu ít được truy cập hoặc kho quá lớn để chuyển một lần.

**Nhược điểm:** đường đọc phức tạp; các truy vấn DBMS lọc trực tiếp theo trường mới có thể bỏ sót tài liệu cũ, vì upcaster chỉ chạy **sau khi đã lấy dữ liệu ra**.

Ví dụ truy vấn lọc `price.amount` sẽ không tìm thấy tài liệu v1 chỉ có `priceVnd`, dù ứng dụng có hàm `toCurrentProduct`. Muốn kết quả đầy đủ phải hỗ trợ cả hai biểu diễn ở truy vấn, dựng một chỉ mục/dữ liệu chuẩn hóa hoặc thực hiện backfill.

### 8.2. Chuyển hàng loạt (*eager/batch migration*)

Chạy công việc đọc các tài liệu v1, chuyển đổi rồi ghi lại theo v2.

**Ưu điểm:** sau khi kết thúc, hệ thống có thể tập trung vào một cấu trúc; index và validation dễ thống nhất hơn.

**Nhược điểm:** có chi phí CPU, I/O, tải ghi, thời gian chạy, rủi ro tranh chấp với cập nhật nghiệp vụ và cần chiến lược khi migration thất bại một phần.

Một migration thực tế cần:

1. Xác định dữ liệu đầu vào và đúng schema version cần đổi.
2. Chuyển từng tài liệu theo cách **idempotent**: chạy lại không tiếp tục làm biến dạng dữ liệu.
3. Ghi có điều kiện để tránh đè cập nhật mới của người dùng trong lúc migration chạy.
4. Theo dõi số tài liệu đã chuyển, lỗi chuyển kiểu, dữ liệu ngoại lệ và tiến độ.
5. Có bước xác nhận các ứng dụng/consumer có thể dùng cấu trúc mới trước khi loại bỏ hỗ trợ cũ.

Không được coi một lệnh `updateMany` là đủ để giải quyết bài toán khi dữ liệu lịch sử có nhiều dạng không đồng nhất.

### 8.3. Ghi định dạng mới, hỗ trợ đọc cả cũ và mới

Một cách chuyển dần phổ biến:

~~~text
Giai đoạn 1: Reader hiểu v1 và v2, writer vẫn ghi v1
Giai đoạn 2: Writer ghi v2, reader vẫn hiểu v1 và v2
Giai đoạn 3: Backfill tài liệu v1 còn lại
Giai đoạn 4: Đo và xác nhận không còn consumer cần v1
Giai đoạn 5: Bỏ logic đọc v1 khi an toàn
~~~

Nếu nhiều phiên bản dịch vụ chạy đồng thời trong quá trình triển khai, cần kiểm tra **tương thích tiến/lùi** giữa writer và reader. Ví dụ, một instance cũ chỉ hiểu `priceVnd` có thể lỗi nếu instance mới vừa chuyển tài liệu sang chỉ có `price.amount`.

### 8.4. Ghi đồng thời hai biểu diễn (*dual-write fields*)

Trong giai đoạn ngắn, một tài liệu có thể chứa cả:

~~~json
{
  "_id": "P-1001",
  "schemaVersion": 2,
  "priceVnd": 8500000,
  "price": {
    "amount": 8500000,
    "currency": "VND"
  }
}
~~~

Điều này giúp một số reader cũ tiếp tục hoạt động, nhưng hai biểu diễn có thể **lệch nhau** khi cập nhật. Cần xác định trường nào là nguồn chính, quy tắc cập nhật cùng lúc và thời điểm loại bỏ trường cũ. Tránh kéo dài dual-write vô thời hạn vì nó biến một tài liệu thành hai nguồn giá trị cạnh tranh.

## 9. Revision: bảo vệ cập nhật đồng thời bằng optimistic concurrency

Một vấn đề khác với schema version là **ghi đè thay đổi của người khác** (*lost update*).

Giả sử sản phẩm hiện có:

~~~json
{
  "_id": "P-1001",
  "schemaVersion": 2,
  "revision": 7,
  "name": "Điện thoại A",
  "attributes": {
    "ramGb": 8,
    "storageGb": 256
  }
}
~~~

Hai người chỉnh sửa:

~~~text
Người A đọc revision 7                 Người B đọc revision 7
   │                                      │
   ▼                                      ▼
Sửa name thành "Điện thoại A Plus"     Sửa ramGb thành 12
   │                                      │
   ▼                                      ▼
Ghi đè toàn tài liệu revision 8        Ghi đè tài liệu từ bản đã đọc
                                          │
                                          ▼
                             Có thể làm mất thay đổi của A
~~~

Giải pháp phổ biến là **optimistic concurrency control (OCC)**: client gửi revision nó đã đọc; DBMS chỉ cập nhật nếu revision hiện tại vẫn đúng. Nếu không còn khớp, ứng dụng báo xung đột hoặc đọc lại rồi giải quyết.

Ví dụ MongoDB với thao tác cập nhật có điều kiện trên **một document**:

~~~javascript
const expectedRevision = 7;

const updated = db.products.findOneAndUpdate(
  {
    _id: "P-1001",
    revision: expectedRevision
  },
  {
    $set: {
      name: "Điện thoại A Plus",
      updatedAt: new Date()
    },
    $inc: {
      revision: 1
    }
  },
  {
    returnDocument: "after"
  }
);

if (updated === null) {
  throw new Error("Tài liệu đã bị thay đổi hoặc không tồn tại");
}
~~~

Ý nghĩa quan trọng:

- Bộ lọc gồm cả `_id` và `revision`; thao tác chỉ khớp nếu tài liệu vẫn ở revision dự kiến.
- `$set` sửa trường cần thay đổi thay vì thay cả tài liệu từ một bản snapshot cũ.
- `$inc` tăng revision trong **cùng lệnh cập nhật**.
- Nếu không tìm thấy document tương ứng, ứng dụng phải xử lý xung đột/mất bản ghi, không âm thầm coi cập nhật thành công.

Ví dụ minh họa theo ngữ nghĩa MongoDB; chi tiết giá trị trả về của `findOneAndUpdate` có thể khác nhau theo driver và tùy chọn phiên bản. Nếu sử dụng API driver, cần kiểm tra kết quả theo hợp đồng của driver thực tế.

### Sửa từng trường có thể tránh một số xung đột nhưng không thay thế OCC

Giả sử A chỉ cập nhật `name`, B chỉ cập nhật `attributes.ramGb` bằng lệnh `$set` riêng. Có những trường hợp cả hai thao tác tồn tại được mà không mất cập nhật. Nhưng nếu một nghiệp vụ cần kiểm tra rằng “RAM và giá phải thay đổi cùng nhau”, chỉ sửa từng trường không bảo vệ toàn bộ bất biến.

**Khi nào dùng OCC?** Khi client đọc dữ liệu, chỉnh sửa rồi lưu về, và việc ghi đè trạng thái mới hơn là không chấp nhận được. OCC đặc biệt hữu ích cho biểu mẫu quản trị, chỉnh cấu hình, hồ sơ hoặc cập nhật từ nhiều thiết bị.

**Khi xung đột xảy ra:** lựa chọn có thể là trả HTTP `409 Conflict`, yêu cầu người dùng tải lại, hiển thị bản khác biệt, hoặc tự hợp nhất khi logic nghiệp vụ đủ rõ. Việc tự động retry bằng cách ghi đè bản mới mà không xét xung đột có thể phá hỏng mục tiêu ban đầu.

### Không để revision biến thành schemaVersion

Nếu đổi tên sản phẩm 100 lần, `revision` có thể lên 107, trong khi `schemaVersion` vẫn là 2. Nếu thay đổi cấu trúc từ v2 lên v3, `schemaVersion` tăng theo hợp đồng dữ liệu; `revision` cũng có thể tăng nếu migration thực hiện ghi thay đổi tài liệu và cơ chế đồng thời đòi hỏi điều đó. Hai số không cần bằng nhau.

## 10. Lưu lịch sử phiên bản: hiện hành, snapshot và bản phát hành nghiệp vụ

**Revision dùng để kiểm tra xung đột** không mặc định có nghĩa hệ thống lưu mọi trạng thái cũ. Nếu chỉ lưu tài liệu hiện hành, sau cập nhật từ revision 7 lên 8, nội dung revision 7 có thể không còn nữa.

Khi nghiệp vụ cần xem “hợp đồng trước khi sửa”, “giá sản phẩm tại thời điểm đặt hàng”, hoặc “ai thay đổi thông số nào”, cần thiết kế **lịch sử** một cách rõ ràng.

### 10.1. Chỉ lưu tài liệu hiện hành

~~~text
products
  P-1001 → revision=8, state hiện tại
~~~

Ưu điểm: đọc/ghi đơn giản, ít dung lượng. Hạn chế: không thể phục hồi nội dung revision 7 chỉ từ tài liệu hiện tại. `updatedAt` cho biết thời gian cập nhật gần nhất nhưng không cho biết giá trị cũ.

### 10.2. Tài liệu hiện hành và collection snapshot bất biến

~~~text
products (hiện hành)
  P-1001 → revision=8

product_revisions (lịch sử)
  (P-1001, 6) → snapshot v6
  (P-1001, 7) → snapshot v7
  (P-1001, 8) → snapshot v8
~~~

Ví dụ một bản lịch sử:

~~~json
{
  "entityId": "P-1001",
  "revision": 7,
  "schemaVersion": 2,
  "recordedAt": "2026-10-12T09:15:00Z",
  "changedBy": "operator:U42",
  "changeReason": "Cập nhật cấu hình sản phẩm",
  "snapshot": {
    "type": "phone",
    "name": "Điện thoại A",
    "attributes": {
      "ramGb": 8,
      "storageGb": 256
    }
  }
}
~~~

Một khóa duy nhất theo `(entityId, revision)` giúp tránh trùng phiên bản lịch sử. Lưu snapshot thuận tiện cho việc đọc trạng thái tại một revision, nhưng tiêu tốn dung lượng nếu mỗi thay đổi nhỏ đều ghi toàn bộ tài liệu. Khi cần giảm dung lượng, có thể cân nhắc lưu thay đổi dạng *diff/delta* và snapshot định kỳ, đổi lại việc khôi phục sẽ phức tạp hơn.

**Lưu ý tính nhất quán:** nếu ứng dụng ghi `products` rồi mới ghi `product_revisions` bằng hai lệnh độc lập, có thể xảy ra lỗi giữa chừng khiến trạng thái hiện hành đổi nhưng lịch sử chưa ghi. Nếu yêu cầu lưu lịch sử đầy đủ, cần thiết kế transaction hoặc cơ chế ghi/phát thay đổi có bảo đảm phù hợp với DBMS. Một lệnh cập nhật nguyên tử trên một document không tự làm cho hai collection được cập nhật nguyên tử.

### Mẫu cập nhật có lưu lịch sử

Ở mức thuật toán:

~~~text
Đầu vào: productId, expectedRevision, patch, actor

BEGIN TRANSACTION (nếu DBMS và cách triển khai hỗ trợ)
  1. Tìm tài liệu theo productId và expectedRevision.
  2. Nếu không khớp → báo conflict, hủy giao dịch.
  3. Áp dụng patch theo quy tắc schema và nghiệp vụ.
  4. Tăng revision, cập nhật updatedAt/updatedBy.
  5. Lưu trạng thái mới vào products.
  6. Ghi snapshot (entityId, newRevision) vào product_revisions.
COMMIT

Sau commit:
  - Nếu cần, phát sự kiện thay đổi qua cơ chế đáng tin cậy.
  - Nếu không thể commit, không công bố cập nhật thành công.
~~~

Thuật toán trên **không phải cú pháp chạy trực tiếp**. Những hệ document khác nhau hỗ trợ transaction và giới hạn khác nhau; triển khai cần xét xử lý retry, lỗi mạng, write concern và việc phát sự kiện ra bên ngoài transaction.

### 10.3. Phiên bản nghiệp vụ là một thực thể độc lập

Không phải mọi “phiên bản” đều chỉ là snapshot kỹ thuật. Ví dụ một hợp đồng có bản chính thức `v1` và `v2`; cả hai có thể cần tồn tại song song vì người dùng đã ký bản v1 và pháp lý không cho phép sửa nội dung đã ký.

Một thiết kế có thể là:

~~~text
contracts
  C-1001 → {currentBusinessVersion:"v2"}

contract_versions
  (C-1001, "v1") → {terms:..., publishedAt:..., immutable:true}
  (C-1001, "v2") → {terms:..., publishedAt:..., immutable:true}
~~~

Ở đây `businessVersion` có nghĩa thuộc **quy trình nghiệp vụ**, không chỉ một bộ đếm số lần ghi. Chỉnh lỗi chính tả ở bản nháp, thay trạng thái phê duyệt và công bố một phiên bản mới có thể là ba thao tác mang quy tắc khác nhau.

## 11. Thời gian và lịch sử: hai loại “khi nào”

Khi lưu tài liệu lịch sử, cần phân biệt:

- **Thời điểm hệ thống ghi nhận** (*recorded/transaction time*): khi dữ liệu được lưu vào hệ thống.
- **Thời điểm hiệu lực nghiệp vụ** (*effective/valid time*): khi một giá trị được coi là đúng trong thực tế hoặc trong hợp đồng.

Ví dụ giá có hiệu lực từ ngày 1 tháng 11, nhưng nhân viên tạo thay đổi vào ngày 28 tháng 10:

~~~json
{
  "productId": "P-1001",
  "businessVersion": "price-2026-11",
  "priceVnd": 9000000,
  "recordedAt": "2026-10-28T04:00:00Z",
  "effectiveFrom": "2026-11-01T00:00:00+07:00"
}
~~~

Trong trường hợp này, `recordedAt` khác `effectiveFrom`. Nếu hỏi “hệ thống **đã biết** giá mới vào ngày nào?”, dùng thời điểm ghi nhận; nếu hỏi “giá **có hiệu lực** lúc 9 giờ sáng ngày 2 tháng 11 là bao nhiêu?”, cần xét thời gian hiệu lực.

Một hệ thống lưu cả hai trục thời gian có thể tiến tới **bitemporal data**, nhưng chỉ có hai trường thời gian không tự đảm bảo trả lời được mọi truy vấn lịch sử. Phải có quy tắc lưu các lần hiệu chỉnh, khoảng hiệu lực không chồng chéo không hợp lệ, timezone, và xác định chính xác bản nào được dùng tại một thời điểm.

### Lịch sử thay đổi khác nhật ký sự kiện

Ví dụ:

~~~text
Snapshot revision 7:
  status = PAID
  shippingAddress = "Đà Nẵng"

Sự kiện:
  OrderPaid
  ShippingAddressCorrected
~~~

Snapshot nói **trạng thái là gì**; sự kiện nói **điều gì đã xảy ra**. Nếu thiết kế event sourcing, sự kiện có thể là nguồn có thẩm quyền để tái dựng trạng thái, và tài liệu hiện hành là projection. Nhưng việc thêm collection lịch sử snapshot không tự biến kiến trúc thành event sourcing.

## 12. Chỉ mục và truy vấn khi thuộc tính, schema hoặc phiên bản thay đổi

Tài liệu có nhiều biến thể khiến chiến lược index quan trọng hơn.

Ví dụ trong MongoDB, ứng dụng tìm điện thoại RAM từ 8 GB:

~~~javascript
db.products.createIndex({
  type: 1,
  "attributes.ramGb": 1
});

db.products.find({
  type: "phone",
  "attributes.ramGb": { $gte: 8 }
});
~~~

Index trên đường dẫn `attributes.ramGb` có thể giúp truy vấn cụ thể. Nhưng tài liệu `shirt` không có trường này; tài liệu cũ có thể lưu RAM dưới tên `specifications.ramGb`; tài liệu lỗi có thể lưu `"8GB"` thay vì số 8.

Những vấn đề cần xử lý:

- **Tên trường thống nhất:** `ramGb`, `ramGB` và `ram_gb` là ba đường dẫn khác nhau.
- **Kiểu dữ liệu thống nhất:** số 8 và chuỗi `"8"` không có cùng hành vi so sánh.
- **Đường dẫn giữa các schema version:** index trên tên mới không tự hỗ trợ truy vấn theo tên cũ.
- **Trường tùy chọn:** có thể dùng index phù hợp với điều kiện có trường hoặc lọc theo `type`, nhưng cần đo chi phí của nó.
- **Mảng và trường lồng nhau:** DBMS có thể tạo index đa giá trị; phải hiểu cách kết hợp điều kiện trên cùng phần tử và giới hạn chỉ mục.
- **Thuộc tính không biết trước:** một số DBMS hỗ trợ wildcard index, nhưng index rất rộng có thể tốn dung lượng và tải ghi; không thay thế thiết kế truy vấn.

Ví dụ MongoDB hỗ trợ wildcard index cho các trường bên trong `attributes`:

~~~javascript
db.products.createIndex({
  "attributes.$**": 1
});
~~~

Đây là một **khả năng của MongoDB**, không phải thuộc tính bắt buộc của mọi document DBMS. Có thể thích hợp với các truy vấn linh hoạt, nhưng cần cân nhắc tần suất lọc, các phép sắp xếp, loại index chuyên dụng, kích thước index và cách dữ liệu thay đổi.

### Truy vấn theo revision

Với collection lịch sử, một index/khoá duy nhất như:

~~~javascript
db.product_revisions.createIndex(
  { entityId: 1, revision: 1 },
  { unique: true }
);

db.product_revisions.find({
  entityId: "P-1001"
}).sort({ revision: -1 }).limit(10);
~~~

có thể hỗ trợ lấy các phiên bản gần nhất của một thực thể. Nếu ứng dụng hỏi “trạng thái tại thời điểm T”, index theo `recordedAt` hoặc `effectiveFrom` và logic chọn phiên bản phù hợp có thể quan trọng hơn số revision.

**Không nên tạo một tài liệu chứa mảng snapshots tăng mãi** cho mọi lần sửa. Tài liệu có giới hạn kích thước theo DBMS, việc cập nhật và đọc cả lịch sử có thể đắt đỏ; lưu mỗi revision thành bản ghi riêng thường giúp phân trang lịch sử, retention và chỉ mục rõ hơn.

## 13. Cập nhật từng phần, thay thế toàn tài liệu và tính nhất quán

Với document DBMS, phải phân biệt ba thao tác:

1. **Cập nhật một trường:** ví dụ đổi `attributes.ramGb`.
2. **Thay toàn tài liệu:** client gửi lại toàn bộ JSON mới.
3. **Thay đổi nhiều tài liệu liên quan:** ví dụ cập nhật sản phẩm và bản lịch sử, hoặc sản phẩm và chỉ mục đọc trong collection khác.

Ví dụ MongoDB:

~~~javascript
db.products.updateOne(
  { _id: "P-1001", revision: 7 },
  {
    $set: {
      "attributes.ramGb": 12,
      updatedAt: new Date()
    },
    $inc: { revision: 1 }
  }
);
~~~

Cập nhật theo đường dẫn có thể giữ nguyên các trường khác trong cùng document. Nhưng nếu logic nghiệp vụ dựa trên hai trường cùng lúc, chẳng hạn `ramGb` phải tương thích `modelCode`, ứng dụng còn cần validate bất biến khi cập nhật.

**Không tự mặc định tính nguyên tử nhiều tài liệu.** Một số document DBMS có transaction nhiều tài liệu với điều kiện riêng; một số triển khai phân tán hạn chế phạm vi atomicity. Trong MongoDB, thao tác cập nhật một document là nguyên tử, còn phối hợp nhiều document với bảo đảm all-or-nothing cần transaction phù hợp.

### Tránh ghi đè vì stale client

Với biểu mẫu chỉnh sản phẩm, client có thể đọc revision 7 rồi giữ bản chỉnh sửa trong 15 phút. Trong lúc đó, dịch vụ khác sửa sản phẩm thành revision 8. Nếu client cũ gửi thao tác thay toàn tài liệu mà không kiểm tra revision, các trường vừa được dịch vụ khác sửa có thể bị mất.

Một hợp đồng API có thể yêu cầu:

~~~http
PATCH /products/P-1001
If-Match: "7"
Content-Type: application/json

{
  "attributes": {
    "ramGb": 12
  }
}
~~~

Đây là minh họa **ý tưởng kiểm tra phiên bản** ở API. HTTP `If-Match` sử dụng entity tag (*ETag*) theo ngữ nghĩa chuẩn; một hệ thống có thể biểu diễn ETag bằng revision nhưng phải định nghĩa/cấp ETag và cách so khớp đúng. Endpoint và payload trên là ví dụ thiết kế API, không phải API chuẩn có sẵn của MongoDB.

## 14. Mở rộng schema an toàn khi nhiều dịch vụ cùng đọc

Một collection có thể được dùng bởi API, hệ thống tìm kiếm, đồng bộ dữ liệu, analytics và tác vụ batch. Khi schema đổi, từng consumer có thể cần thời gian nâng cấp khác nhau.

Ví dụ luồng dữ liệu:

~~~text
              products collection
                     │
         ┌───────────┼─────────────┐
         ▼           ▼             ▼
     Product API   Search index   Analytics ETL
       (v2)          (v1)            (v1)
~~~

Nếu thay `priceVnd` bằng `price.amount` ngay khi Product API đổi sang v2, Search và Analytics đang đọc v1 có thể gặp dữ liệu thiếu. Quy trình chuyển schema nên bao gồm:

- **Kiểm kê các reader/writer:** dịch vụ, script, công việc batch, công cụ xuất dữ liệu, báo cáo.
- **Xác định tính tương thích:** client cũ có chấp nhận trường mới? Có còn viết trường cũ và làm mất trường mới không?
- **Dùng triển khai nhiều giai đoạn:** triển khai reader hỗ trợ nhiều version, rồi writer mới, rồi backfill dữ liệu, cuối cùng mới bỏ hỗ trợ cũ.
- **Quy định nguồn sự thật:** nếu có hai biểu diễn tạm thời, nơi nào quyết định giá trị đúng?
- **Theo dõi tiến độ:** tỷ lệ tài liệu v1/v2, lỗi upcast, tình trạng index, consumer lag, kết quả đối soát.
- **Có cơ chế xử lý bản lỗi:** tài liệu không đủ thông tin để chuyển phải được báo, cách ly hoặc xử lý bằng quy tắc nghiệp vụ, không tự bịa giá trị.

Nếu schema mới cho phép thuộc tính hoàn toàn do người dùng tạo, cần cân nhắc tác động lên dữ liệu xuất ra và consumer. Ví dụ tên trường tùy ý có thể trùng với trường dành riêng của hệ thống hoặc gây tăng số lượng đường dẫn index không kiểm soát.

## 15. Bảo mật, lưu giữ và khả năng kiểm toán của tài liệu phiên bản

Lưu snapshot lịch sử làm tăng lượng dữ liệu và đôi khi giữ lại **thông tin đã bị sửa hoặc xóa khỏi tài liệu hiện hành**. Điều này ảnh hưởng đến quyền truy cập, bảo vệ dữ liệu và yêu cầu xóa theo chính sách.

Ví dụ, nếu người dùng sửa địa chỉ giao hàng và hệ thống giữ mọi snapshot, địa chỉ cũ vẫn còn trong collection lịch sử. Cần xác định rõ:

1. Ai được đọc và ai được sửa **lịch sử**?
2. Có trường nào không được sao chép vào snapshot, ví dụ access token hoặc thông tin bí mật?
3. Lịch sử được giữ bao lâu? Có quy tắc xóa/ẩn thông tin nhạy cảm không?
4. Khi schema thay đổi, các snapshot cũ có còn giải mã/hiển thị đúng không?
5. Nếu tài liệu hiện hành bị xóa theo yêu cầu hợp lệ, các bản sao, index, backup và snapshot liên quan xử lý thế nào?
6. Thông tin `changedBy`, `changeReason`, `recordedAt` có được ghi từ nguồn tin cậy hay do client tự khai báo?

Với yêu cầu kiểm toán chặt chẽ, chỉ lưu các bản snapshot sửa được trong collection thường chưa đủ để chứng minh lịch sử không bị thay đổi. Cần cơ chế phân quyền, lưu trữ, chống sửa đổi hoặc đối soát phù hợp với yêu cầu thực tế. Điều này phải được xác định trong thiết kế, không tự phát sinh từ trường `revision`.

## 16. Tình huống tổng hợp: hồ sơ sản phẩm phát triển qua nhiều phiên bản

Giả sử một cửa hàng bán điện thoại, laptop và phụ kiện. Ở giai đoạn đầu, mỗi sản phẩm chỉ có tên, giá VND và vài thông số. Sau sáu tháng, hệ thống cần hỗ trợ nhiều đơn vị tiền tệ, thương hiệu, thông số thay đổi theo loại và lịch sử chỉnh sửa phục vụ đối soát.

Một tài liệu hiện hành có thể được thiết kế:

~~~json
{
  "_id": "P-1001",
  "tenantId": "T-01",
  "type": "phone",
  "schemaVersion": 2,
  "revision": 8,
  "name": "Điện thoại A Plus",
  "status": "ACTIVE",
  "price": {
    "amount": 9000000,
    "currency": "VND"
  },
  "attributes": {
    "ramGb": 12,
    "storageGb": 256,
    "supportsEsim": true
  },
  "createdAt": "2026-09-01T08:00:00Z",
  "updatedAt": "2026-11-01T03:00:00Z"
}
~~~

Kế hoạch thiết kế có thể là:

1. **Danh tính ổn định:** `_id` là mã sản phẩm, `tenantId` giúp xác định phạm vi sở hữu; xác thực và phân quyền vẫn được kiểm tra ở tầng phù hợp.
2. **Lõi chung:** `type`, `name`, `status`, `price`, timestamps.
3. **Thuộc tính chuyên biệt:** `attributes` theo schema của từng `type`; giá trị có kiểu và đơn vị rõ ràng.
4. **Schema version:** `schemaVersion` ghi cách đọc tài liệu; reader hỗ trợ v1/v2 trong giai đoạn chuyển đổi.
5. **Concurrency revision:** `revision` tăng khi lưu thay đổi theo hợp đồng; cập nhật có điều kiện tránh ghi đè stale.
6. **Lịch sử:** collection `product_revisions` chứa snapshot theo `entityId` và `revision` nếu nghiệp vụ cần tra cứu bản cũ.
7. **Index theo truy vấn:** ID để xem chi tiết; `tenantId + type + status` cho danh sách; trường `attributes.ramGb` nếu cần lọc điện thoại theo RAM.
8. **Migration:** backfill tài liệu v1 sau khi reader mới đã được triển khai, kiểm soát xung đột và theo dõi tài liệu lỗi.

### Ví dụ câu hỏi đọc tài liệu

**“Sản phẩm P-1001 hiện có những thông số gì?”** → đọc tài liệu hiện hành theo `_id`, xử lý dựa trên `schemaVersion`, hiển thị `attributes` theo `type`.

**“Tìm điện thoại RAM từ 8 GB trong tenant T-01.”** → truy vấn theo `tenantId`, `type` và `attributes.ramGb`; phải bảo đảm các tài liệu cũ được bao phủ, hoặc thông báo rõ phạm vi dữ liệu đã migrate.

**“Ai đổi RAM từ 8 GB thành 12 GB?”** → chỉ `revision = 8` không trả lời được; cần lịch sử có actor/timestamp/diff hoặc audit event tương ứng.

**“Làm cách nào giữ mọi thay đổi khi hai quản trị viên chỉnh sản phẩm?”** → dùng cập nhật có điều kiện theo revision và chính sách xử lý xung đột, hoặc cơ chế giao dịch thích hợp.

**“Nếu thay thuộc tính của điện thoại, các đơn hàng cũ có bị đổi theo không?”** → phụ thuộc đơn hàng nhúng snapshot thông tin sản phẩm tại thời điểm mua hay tham chiếu đến tài liệu sản phẩm hiện tại. Với thông tin giá/thuế/tên hàng cần bất biến theo giao dịch, nên xác định rõ **dữ liệu chốt tại thời điểm mua** thay vì luôn đọc giá hiện hành.

## 17. Những nhầm lẫn cần tránh

| Nhận định dễ nhầm | Cách hiểu chính xác hơn |
| --- | --- |
| “Document DBMS không cần schema.” | Schema vẫn tồn tại ở dạng hợp đồng dữ liệu, validation và quy tắc nghiệp vụ, dù DBMS cho phép cấu trúc linh hoạt. |
| “Tài liệu cùng collection có thể có kiểu bất kỳ mà không ảnh hưởng ứng dụng.” | Trường thiếu, sai kiểu hoặc khác cấu trúc có thể gây lỗi truy vấn, index và consumer. |
| “Có `updatedAt` là đã có versioning.” | Một timestamp không lưu snapshot cũ hoặc ngăn mất cập nhật. |
| “`schemaVersion` tăng sau mỗi lần sửa.” | Schema version ghi phiên bản cấu trúc; revision mới thường tăng theo lần sửa của tài liệu. |
| “`revision` là lịch sử.” | Revision là chỉ số/điều kiện kiểm tra cập nhật; muốn đọc bản cũ phải lưu lịch sử riêng. |
| “Tất cả chỉnh sửa phải ghi đè nguyên document.” | Nhiều DBMS cho cập nhật một đường dẫn/trường, vẫn phải xét ranh giới atomicity và nghiệp vụ. |
| “Đã có upcaster thì truy vấn theo trường mới tìm được mọi tài liệu cũ.” | Upcaster thường chạy sau khi đọc; DBMS vẫn phải tìm đúng bản ghi theo biểu diễn đang được lưu. |
| “Giữ mọi snapshot luôn an toàn.” | Snapshot có chi phí lưu trữ, thông tin nhạy cảm, quyền truy cập và chính sách retention. |
| “Đổi schema không ảnh hưởng index.” | Tên, kiểu và cấu trúc trường có thể đổi, khiến index/truy vấn cũ kém hữu ích hoặc không đúng. |
| “MongoDB tự giải quyết mọi xung đột cập nhật.” | Một thao tác đơn có bảo đảm atomicity, nhưng luồng đọc–sửa–ghi từ nhiều client vẫn cần thiết kế OCC hoặc cơ chế tương đương. |

## 18. Bài tập thực hành

### Bài 1 — Thuộc tính thay đổi theo loại

Hệ thống có ba loại sản phẩm: điện thoại (RAM, bộ nhớ), áo (size, chất liệu), sách (ISBN, số trang). Hãy thiết kế một cấu trúc tài liệu có lõi chung và `attributes`. Chỉ ra trường nào bắt buộc ở tất cả sản phẩm, trường nào chỉ bắt buộc khi `type` có giá trị cụ thể.

**Gợi ý:** có thể dùng `_id`, `type`, `name`, `status` làm lõi; `attributes` được validation theo loại. Đừng yêu cầu áo có `ramGb` hoặc điện thoại có `isbn`.

### Bài 2 — Phân biệt missing và null

Ba tài liệu điện thoại có `supportsEsim` lần lượt bằng `true`, `null` và hoàn toàn thiếu trường. Hãy nêu những cách hiểu nghiệp vụ có thể xảy ra và lý do không nên mặc định hai trường hợp cuối bằng `false`.

**Gợi ý:** `null` và missing có thể biểu diễn “chưa biết”, “không áp dụng”, “chưa nhập”, “dữ liệu phiên bản cũ”. Cần hợp đồng schema để diễn giải.

### Bài 3 — Hai loại phiên bản

Một tài liệu có `schemaVersion = 3`, `revision = 45`. Nhân viên chỉ sửa tên sản phẩm. Theo thiết kế OCC thông thường, giá trị nào nên thay đổi? Một tuần sau, hệ thống đổi cấu trúc giá sang đối tượng mới. Giá trị nào cần xem xét đổi?

**Gợi ý:** sửa tên thường tăng `revision` nhưng không đổi `schemaVersion`; thay schema cần thay `schemaVersion`, và migration có thể tác động revision nếu đó là một lần ghi theo hợp đồng cập nhật.

### Bài 4 — Truy vấn tài liệu cũ

Collection có 30% tài liệu v1 sử dụng `priceVnd` và 70% tài liệu v2 sử dụng `price.amount`. Một màn hình chỉ truy vấn `price.amount >= 1000000`. Vì sao kết quả có thể thiếu dù ứng dụng biết upcast v1?

**Gợi ý:** bộ lọc chạy trong DBMS trên biểu diễn đang lưu trước khi upcaster có cơ hội chuyển dữ liệu. Cần truy vấn hỗ trợ cả hai phiên bản, migration hoặc read model chuẩn hóa.

### Bài 5 — Mất cập nhật

Hai quản trị viên cùng đọc sản phẩm revision 8, một người đổi tên, người kia đổi RAM. Cả hai thay toàn tài liệu. Hãy mô tả trường hợp mất cập nhật và đề xuất bộ lọc cập nhật theo `_id` và `revision`.

**Gợi ý:** request đầu thành công khi revision còn 8 và tăng lên 9; request sau với điều kiện revision 8 không khớp, phải báo conflict thay vì âm thầm ghi đè.

### Bài 6 — Lịch sử có bảo đảm

Yêu cầu pháp lý cần xem mọi phiên bản hợp đồng đã công bố. Chỉ lưu tài liệu `contracts` hiện hành với `revision` tăng dần đã đủ chưa? Nếu lưu thêm collection lịch sử, điều gì xảy ra nếu ghi hiện hành thành công nhưng ghi lịch sử thất bại?

**Gợi ý:** chưa đủ; cần lưu bản công bố bất biến và bảo đảm nhất quán giữa bản chính/bản lịch sử theo kiến trúc, ngoài các quy tắc quyền truy cập và retention.

## 19. Khung quyết định khi thiết kế tài liệu có thuộc tính thay đổi

Với mỗi loại thực thể, có thể ghi một đặc tả ngắn:

~~~yaml
entity: Product
identity: "_id (stable per tenant)"
commonFields:
  - tenantId
  - type
  - name
  - status
variantFields: "attributes, validated according to type"
currentSchemaVersion: 2
schemaCompatibility: "Readers accept v1 and v2 during migration"
concurrency:
  mechanism: "Optimistic revision check"
  conflictHandling: "Reject stale edits and request reload/merge"
history:
  enabled: true
  storage: "Separate immutable snapshots keyed by entityId + revision"
  retention: "According to product/business policy"
queries:
  - "Find by _id"
  - "List by tenantId + type + status"
  - "Filter phones by attributes.ramGb"
migration:
  strategy: "Read both, write new, backfill old"
~~~

Đây là **mẫu tài liệu thiết kế**, không phải cấu hình sẵn có của một DBMS. Trước triển khai, cần bổ sung schema thực tế, bảo đảm transaction, cơ chế phân quyền, chỉ số tải và phương án khôi phục.

Điểm cốt lõi là tách bạch ba quyết định: **biểu diễn những thuộc tính biến thiên như thế nào**, **diễn giải và chuyển đổi schema qua các lần phát triển ra sao**, và **theo dõi sửa đổi/lịch sử bằng cơ chế nào**. Một thiết kế tài liệu NoSQL tốt không dựa đơn thuần vào khả năng thêm trường tùy ý, mà dựa vào danh tính ổn định, hợp đồng dữ liệu rõ ràng, thao tác cập nhật an toàn và cách truy vấn đúng qua nhiều phiên bản.
