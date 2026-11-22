# Phát hiện dữ liệu không đồng nhất và kế hoạch chuẩn hóa

Một ưu điểm lớn của NoSQL là khả năng tiếp nhận dữ liệu có cấu trúc linh hoạt. Trong document database, hai document thuộc cùng collection có thể chứa những trường khác nhau; một trường có thể xuất hiện dưới dạng chuỗi ở tài liệu cũ và số ở tài liệu mới; một đối tượng có thể được nhúng ở phiên bản trước nhưng chuyển thành tham chiếu ở phiên bản sau. Sự linh hoạt ấy hữu ích khi ứng dụng phát triển, nhưng cũng khiến **schema drift** — sai khác giữa dữ liệu thực tế và quy ước dữ liệu mà ứng dụng kỳ vọng — tích lũy theo thời gian.

Ví dụ, một hệ thống bán hàng muốn tính tổng doanh thu nhưng có các document lưu giá trị đơn hàng lần lượt là **120000**, **"120000"**, **"120.000"** và **null**. Trên giao diện, người dùng có thể từng thấy cả bốn là “120.000 đ” hoặc “không có dữ liệu”; trong database, chúng không hề đồng nghĩa. Cố gắng cộng tất cả như số có thể tạo lỗi chuyển kiểu, bỏ sót dữ liệu hoặc ghi nhận doanh thu sai.

Vì vậy, chuẩn hóa không phải thao tác **ép toàn bộ dữ liệu về một kiểu rồi chạy updateMany**. Một kế hoạch tốt phải bắt đầu bằng **phát hiện và phân loại biến thể**, thiết lập **hợp đồng schema đích**, xác định **quy tắc chuyển đổi không làm thay đổi ý nghĩa nghiệp vụ**, sau đó triển khai **backfill có kiểm soát, tương thích phiên bản, giám sát và phương án hồi phục**.

Bài học dùng MongoDB làm ví dụ kỹ thuật chính, sau đó đối chiếu với DynamoDB, Redis và Cassandra để thấy rằng dữ liệu không đồng nhất không chỉ xuất hiện ở document store. Các câu lệnh là minh họa trên dữ liệu thử nghiệm; mọi kế hoạch sửa dữ liệu thật phải dùng quy tắc nghiệp vụ và giới hạn phù hợp hệ đang vận hành.

## 1. Dữ liệu không đồng nhất là gì?

**Dữ liệu không đồng nhất (heterogeneous data)** là tập bản ghi có cùng mục đích nghiệp vụ nhưng khác nhau về kiểu, hình dạng, quy ước giá trị, đơn vị, mã hóa hoặc ý nghĩa của các trường.

Ví dụ hai bản ghi cùng là đơn hàng nhưng có cách biểu diễn khác nhau:

~~~javascript
// Bản ghi cũ
{
  _id: "order-1001",
  tenantId: "shop-a",
  total: "120000",
  status: "paid",
  createdAt: "2026-11-10 09:30:00",
  customer: { id: "customer-07", name: "An" }
}

// Bản ghi mới
{
  _id: "order-1002",
  tenantId: "shop-a",
  totalMinor: NumberLong("120000"),
  currency: "VND",
  status: "PAID",
  createdAt: ISODate("2026-11-10T09:30:00Z"),
  customerId: "customer-07",
  schemaVersion: 2
}
~~~

Cả hai cùng mô tả một đơn hàng đã thanh toán nhưng khác ở ít nhất năm chiều:

1. **Tên trường:** total so với totalMinor.
2. **Kiểu dữ liệu:** chuỗi so với số nguyên BSON long.
3. **Tập giá trị:** paid so với PAID.
4. **Kiểu và ngữ nghĩa thời gian:** chuỗi không có múi giờ so với BSON Date biểu diễn một thời điểm UTC.
5. **Cấu trúc quan hệ:** object customer nhúng so với customerId tham chiếu.

Việc quyết định hai bản ghi này tương đương **không thể chỉ dựa vào cú pháp**. Chẳng hạn, chuỗi **"2026-11-10 09:30:00"** thiếu thông tin múi giờ. Nếu dữ liệu cũ được ghi theo giờ Việt Nam, chuyển thẳng thành **09:30 UTC** sẽ làm sai thời điểm thực tế bảy giờ.

**Chuẩn hóa schema** trong bài là đưa dữ liệu về **một hợp đồng biểu diễn thống nhất** theo ý nghĩa nghiệp vụ. Khái niệm này khác với **normalization trong cơ sở dữ liệu quan hệ**, vốn thường tập trung tách các phụ thuộc dữ liệu để giảm trùng lặp. Hai chủ đề liên quan nhưng không đồng nhất.

## 2. Phân loại các kiểu không đồng nhất

| Loại sai khác | Ví dụ | Hệ quả thường gặp |
|---|---|---|
| **Thiếu trường** | Không có currency hoặc schemaVersion | Logic dùng giá trị mặc định không rõ, lọc thiếu bản ghi |
| **Null khác missing** | status: null so với không có status | Khó phân biệt “chưa biết” và “không được ghi” |
| **Sai kiểu** | quantity: "3" thay vì 3 | Phép tính, so sánh và index có kết quả khác |
| **Nhiều tên cho cùng nghĩa** | total, amount, totalMinor | Query phải dùng nhiều nhánh hoặc bỏ sót |
| **Định dạng không thống nhất** | "2026-11-10", ISO Date, epoch milliseconds | Sort thời gian và cửa sổ báo cáo sai |
| **Khác đơn vị** | giá VND nguyên đồng, USD theo cent, nhiệt độ °C/°F | Tổng hợp số học sai dù tất cả đều là number |
| **Enum không chuẩn** | paid, PAID, completed, "Đã thanh toán" | Lọc theo status không đầy đủ |
| **Object/mảng biến thể** | items là object đơn lẻ hoặc array | Code duyệt dữ liệu lỗi hoặc bỏ qua |
| **Tham chiếu khác kiểu** | customerId String, ObjectId, object customer | Join, lookup và xóa theo chủ thể khó |
| **Khác ngữ nghĩa** | total là subtotal ở bản cũ nhưng grand total ở bản mới | Cùng kiểu mà công thức báo cáo sai |
| **Trùng danh tính** | Hai bản ghi cùng externalOrderId | Đếm đôi, khó tạo unique index |
| **Mã hóa/locale** | dấu phẩy ngăn thập phân hoặc phân tách hàng nghìn | Chuyển số mơ hồ |
| **Đối tượng lồng nhau thay đổi** | shipping.address so với deliveryAddress | Lỗi cập nhật field và API cũ không đọc được |
| **Dữ liệu dẫn xuất bị lệch** | order.total khác tổng items | Bất biến nghiệp vụ không được giữ |

Trong thực tế, một document có thể mắc nhiều loại cùng lúc. Ví dụ **status = "paid"** và **createdAt** sai múi giờ tạo ra một bản ghi vừa sai enum vừa không thể đưa chắc chắn vào báo cáo theo ngày.

## 3. Tại sao NoSQL dễ xuất hiện schema drift?

Một số nguồn thường gặp:

- Ứng dụng đã triển khai **nhiều phiên bản writer** cùng lúc: web, mobile, worker, batch job.
- Một phiên bản mới đổi field nhưng bản cũ **vẫn tiếp tục ghi theo schema cũ**.
- Dữ liệu đến từ **đối tác/API bên ngoài** có định dạng và quy ước khác nhau.
- Một tác vụ **import/migration** ghi thẳng vào database, bỏ qua validation tại API.
- Cơ sở dữ liệu cho phép **schema linh hoạt** và không có hợp đồng kiểu được cưỡng chế ở mọi đường ghi.
- Phần mềm từng sử dụng **giá trị mặc định ngầm** mà không ghi rõ vào document.
- Dữ liệu **lịch sử** được tạo trước khi quy tắc nghiệp vụ hiện tại tồn tại.
- Các pipeline **CDC, cache, analytics và replay** phát lại phiên bản dữ liệu không còn tương thích.
- Những người bảo trì khác nhau hiểu **cùng tên trường** theo những ý nghĩa khác nhau.

Hậu quả thường không xuất hiện ngay khi ghi. Dữ liệu có thể được lưu nhiều tháng rồi gây lỗi khi một tính năng mới dùng **aggregation**, **sort**, **join** hoặc cố tạo **unique index**.

Ví dụ, truy vấn **db.orders.find({status: "PAID"})** sẽ không trả các bản ghi có **status: "paid"** nếu ứng dụng không chuẩn hóa hoặc query không nêu đủ biến thể. Dữ liệu “vẫn có ở database” nhưng đã **biến mất khỏi báo cáo theo trạng thái**.

## 4. Chốt hợp đồng dữ liệu đích trước khi sửa bản ghi

Đừng bắt đầu bằng câu lệnh update. Hãy định nghĩa document chuẩn với ý nghĩa rõ:

~~~javascript
{
  _id: "order-1002",
  tenantId: "shop-a",
  customerId: "customer-07",
  items: [
    {
      sku: "BOOK-01",
      quantity: 2,
      unitPriceMinor: NumberLong("60000")
    }
  ],
  totalMinor: NumberLong("120000"),
  currency: "VND",
  status: "PAID",
  createdAt: ISODate("2026-11-10T09:30:00Z"),
  schemaVersion: 2
}
~~~

**Hợp đồng đích** nên trả lời:

| Trường | Kiểu/điều kiện đề xuất | Ngữ nghĩa |
|---|---|---|
| _id | Định danh ổn định, duy nhất | Không thay khi chuẩn hóa nếu không bắt buộc |
| tenantId | String không rỗng | Phạm vi sở hữu và phân quyền |
| customerId | String hoặc kiểu ID thống nhất theo thiết kế | Tham chiếu khách hàng, kiểm tra đúng tenant |
| items | Array, có thể yêu cầu không rỗng | Dòng hàng chốt ở thời điểm mua |
| items.quantity | Số nguyên dương | Số lượng theo đơn vị bán |
| items.unitPriceMinor | Số nguyên theo đơn vị tiền nhỏ nhất | Giá lịch sử của một đơn vị hàng |
| totalMinor | Số nguyên theo cùng đơn vị tiền | Tổng thanh toán theo công thức nghiệp vụ |
| currency | Mã tiền tệ có hợp đồng rõ | Không được tự suy ra cho dữ liệu đa tiền tệ |
| status | Một giá trị trong enum chính thức | Trạng thái đơn theo state machine |
| createdAt | BSON Date | Thời điểm tuyệt đối có timezone đã diễn giải đúng |
| schemaVersion | Số nguyên phiên bản | Cho phép đọc và chuyển đổi dữ liệu có kiểm soát |

**Không phải tất cả record đều có thể chuyển đổi tự động.** Hợp đồng còn phải chỉ rõ trường hợp nào **được chuyển chắc chắn**, trường hợp nào **cần tra cứu nguồn gốc**, và trường hợp nào **không được suy đoán**.

Nếu dữ liệu cũ không có currency mà một tenant từng bán USD và VND, việc tự điền **VND** có thể làm sai báo cáo tài chính. Nếu có chứng từ hoặc phiên bản ứng dụng chứng minh mọi đơn trước một ngày nhất định của một tenant đều dùng VND, quy tắc có thể được áp dụng cho **đúng phạm vi đó**, kèm dấu vết nguồn quyết định.

## 5. Thiết lập bộ dữ liệu khảo sát có chủ đích

Tạo một tập giả lập trên database thử nghiệm:

~~~javascript
db.ordersRaw.insertMany([
  {
    _id: "r1", tenantId: "shop-a",
    total: "120000", currency: "VND",
    status: "paid",
    createdAt: "2026-11-10T09:30:00Z",
    customerId: "customer-07"
  },
  {
    _id: "r2", tenantId: "shop-a",
    totalMinor: NumberLong("250000"), currency: "VND",
    status: "PAID",
    createdAt: ISODate("2026-11-11T10:00:00Z"),
    customerId: "customer-09",
    schemaVersion: 2
  },
  {
    _id: "r3", tenantId: "shop-a",
    total: "120.000", currency: "VND",
    status: "Đã thanh toán",
    createdAt: "10/11/2026 16:30",
    customer: { id: "customer-07" }
  },
  {
    _id: "r4", tenantId: "shop-a",
    total: null,
    status: "pending",
    createdAt: null,
    customerId: "customer-10"
  },
  {
    _id: "r5", tenantId: "shop-b",
    total: 125.50, currency: "USD",
    status: "paid",
    createdAt: 1794303000000,
    customerId: "customer-02"
  },
  {
    _id: "r6", tenantId: "shop-b",
    total: { value: "39.99", currency: "USD" },
    status: "PAID",
    createdAt: "2026-11-10T09:30:00-05:00",
    customerId: "customer-03"
  }
]);
~~~

Những document này **cố tình không thống nhất**. Chúng dùng để khảo sát, **không phải tập dữ liệu đã được chuẩn hóa**.

Các vấn đề phát hiện được bằng mắt:

- **r1** có total dạng chuỗi số, status chữ thường và thời gian ISO có múi giờ.
- **r2** đã dùng totalMinor long, status chuẩn và BSON Date.
- **r3** có dấu chấm trong số và thời gian dạng ngày/tháng/năm không kèm timezone; không thể tự kết luận cách parse nếu thiếu nguồn.
- **r4** không có currency, total và createdAt là null.
- **r5** có số thực USD và timestamp số; cần biết số đang ở **đô la hay cent**, timestamp là **mili giây hay giây**, không chỉ biết chúng là number.
- **r6** dùng object cho total và chuỗi thời gian có offset.

Đây là lý do khảo sát phải có cả **kiểu thực tế** và **ngữ nghĩa từng biến thể**, thay vì chỉ đếm số document.

## 6. Phát hiện field thiếu, null và các kiểu BSON

MongoDB cung cấp **$exists** ở truy vấn và **$type** trong aggregation. Trước khi chuẩn hóa, nên tách bạch:

~~~javascript
// Trường total hoàn toàn không tồn tại
db.ordersRaw.find({ total: { $exists: false } });

// Trường total tồn tại và có giá trị null
db.ordersRaw.find({ total: { $type: "null" } });

// Tìm mọi record có kiểu total là string
db.ordersRaw.find({ total: { $type: "string" } });
~~~

Lưu ý: biểu thức **{total: null}** trong truy vấn MongoDB thường khớp cả document có trường null **và** document thiếu trường, vì vậy không nên dùng nó để phân biệt hai trường hợp. Khi cần chính xác, dùng **$exists** hoặc **$type** theo mục đích.

Một pipeline kiểm kê kiểu tổng tiền:

~~~javascript
db.ordersRaw.aggregate([
  {
    $project: {
      totalType: { $type: "$total" },
      totalMinorType: { $type: "$totalMinor" },
      statusType: { $type: "$status" },
      createdAtType: { $type: "$createdAt" }
    }
  },
  {
    $group: {
      _id: {
        total: "$totalType",
        totalMinor: "$totalMinorType",
        status: "$statusType",
        createdAt: "$createdAtType"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

Trong aggregation, **$type** có thể trả **"missing"** với đường dẫn không tồn tại. Với số, nó phân biệt các kiểu BSON như **int**, **long**, **double**, **decimal**; các kiểu này có miền giá trị và cách xử lý số khác nhau.

Kết quả kiểm kê giúp biết **bao nhiêu nhóm cấu trúc** cần xem. Nhưng một tập kiểu giống nhau chưa có nghĩa nội dung hợp lệ: hai chuỗi **"120000"** và **"12O000"** đều có type string; ký tự **O** trong chuỗi thứ hai không phải chữ số 0.

## 7. Đếm enum thực tế, kể cả missing

Với trạng thái đơn, bước tiếp theo là xem những giá trị thật xuất hiện trong dữ liệu:

~~~javascript
db.ordersRaw.aggregate([
  {
    $project: {
      normalizedDisplay: {
        $cond: [
          { $eq: [{ $type: "$status" }, "missing"] },
          "<MISSING>",
          {
            $cond: [
              { $eq: ["$status", null] },
              "<NULL>",
              "$status"
            ]
          }
        ]
      }
    }
  },
  {
    $group: {
      _id: "$normalizedDisplay",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
~~~

Bảng ánh xạ **chỉ nên được tạo sau khi nghiệp vụ xác nhận ý nghĩa**:

| Giá trị nguồn | Giá trị đích ứng viên | Điều kiện |
|---|---|---|
| PAID | PAID | Đã ở dạng chuẩn |
| paid | PAID | Nếu thực sự là trạng thái đã thanh toán |
| Đã thanh toán | PAID | Chỉ khi hệ thống cũ sử dụng cùng định nghĩa |
| pending | PENDING | Nếu đúng “đang chờ” theo state machine mới |
| completed | Không tự quyết | Có hệ coi là thanh toán xong, có hệ coi là giao hàng xong |
| null hoặc missing | Không tự điền | Cần xác minh nguồn, thời điểm và loại đơn |
| chuỗi lạ | QUARANTINE hoặc xử lý thủ công | Không suy ra từ cách viết tương tự |

Đừng dùng một quy tắc **toUpperCase** rồi nghĩ đã chuẩn hóa enum. **"COMPLETED"**, **"SETTLED"** và **"PAID"** có thể là ba trạng thái nghiệp vụ hoàn toàn khác nhau.

## 8. Khảo sát theo tenant, thời kỳ và phiên bản writer

Một collection có thể nhìn chung “90% hợp lệ” nhưng một tenant hoặc một khoảng thời gian lại chứa gần như toàn bộ lỗi. Phân tích theo **nguồn gốc và thời điểm ghi** giúp tìm nơi gây drift:

~~~javascript
db.ordersRaw.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        totalType: { $type: "$total" },
        statusType: { $type: "$status" },
        createdAtType: { $type: "$createdAt" }
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { "_id.tenantId": 1, count: -1 } }
]);
~~~

Khi có các trường **writerVersion**, **sourceSystem**, **importBatchId** hoặc **ingestedAt** đáng tin cậy, có thể nhóm theo chúng để xác định chính xác writer cũ cần sửa. Nhưng không được dùng **createdAt đang sai kiểu** làm cơ sở phân nhóm thời gian trước khi bảo đảm cách diễn giải timestamp.

Các câu hỏi cần trả lời:

- Biến thể có bắt đầu sau một đợt triển khai hay import cụ thể không?
- Có phải chỉ từ một thiết bị/SDK/phiên bản mobile không?
- Hệ thống hiện còn ghi dữ liệu theo schema cũ không?
- Có hai writer cùng sử dụng một collection với quy tắc tiền tệ khác nhau không?
- Bản ghi lỗi thuộc dữ liệu cần giữ lâu dài hay cache có thể dựng lại?

Nếu **nguồn ghi sai vẫn còn hoạt động**, chỉ chạy backfill sẽ không sửa được vấn đề. Dữ liệu mới sẽ tiếp tục drift ngay sau khi chuyển dữ liệu cũ.

## 9. Khảo sát toàn bộ hay lấy mẫu?

Một collection hàng trăm triệu record không nhất thiết phải quét toàn bộ nhiều lần ngay từ đầu. Có thể kết hợp:

**Giai đoạn thăm dò:** lấy mẫu ngẫu nhiên hoặc phân tầng theo tenant, thời gian, nguồn. Dùng mẫu để khám phá loại lỗi và thiết kế phép đo.

**Giai đoạn định lượng:** chạy những phép đếm chuyên biệt qua index, aggregation hoặc job dữ liệu có giới hạn tài nguyên để xác nhận phân bố trên toàn phạm vi cần xử lý.

**Giai đoạn kiểm tra kết quả:** sau backfill, kiểm kê lại cùng chỉ số trên tập đã chuyển và đối soát với số lượng ban đầu.

Ví dụ lấy mẫu bằng **$sample**:

~~~javascript
db.ordersRaw.aggregate([
  { $sample: { size: 1000 } },
  {
    $project: {
      tenantId: 1,
      totalType: { $type: "$total" },
      statusType: { $type: "$status" },
      createdAtType: { $type: "$createdAt" },
      schemaVersion: 1
    }
  }
]);
~~~

Nếu collection có dưới 1.000 document, sample chỉ có thể lấy tối đa số bản ghi hiện hữu. Với tập dữ liệu lớn, điều kiện và cách thực hiện **$sample** phụ thuộc kích thước, vị trí trong pipeline và optimizer; cũng không được xem một sample là toàn bộ phân bố đúng của từng tenant nhỏ.

**Mẫu nhỏ rất hữu ích để khám phá dạng lỗi, nhưng không đủ chứng minh tỉ lệ lỗi hiếm bằng 0.** Những trường hợp liên quan tài chính, phân quyền và xóa dữ liệu cần kế hoạch kiểm chứng chặt hơn.

## 10. Chuyển kiểu số: chỉ ép khi đã hiểu đơn vị

Giả sử hợp đồng đích là **totalMinor** dạng số nguyên theo đơn vị tiền nhỏ nhất.

Những giá trị nguồn:

~~~text
"120000"    -> có thể là 120.000 đơn vị nhỏ nhất
"120.000"   -> có thể là 120.000 theo cách nhóm hàng nghìn,
               hoặc 120.000 theo cách viết số thập phân của locale khác
120000      -> số nguyên, nhưng đơn vị là đồng hay cent?
125.50      -> có thể là 125,50 USD hoặc 12.550 cent?
"12O000"    -> chứa chữ O, không phải số hợp lệ
null        -> thiếu thông tin
~~~

Một quy tắc tự động an toàn nên **giới hạn phạm vi đầu vào**. Ví dụ chỉ chấp nhận chuỗi gồm toàn chữ số, không có dấu phân cách, nếu có bằng chứng chúng biểu diễn số nguyên đơn vị nhỏ nhất:

~~~javascript
function parseMinorUnits(rawValue) {
  if (typeof rawValue === "string" && /^[0-9]+$/.test(rawValue)) {
    const number = Number(rawValue);
    if (Number.isSafeInteger(number)) {
      return number;
    }
  }
  if (typeof rawValue === "number" &&
      Number.isSafeInteger(rawValue) && rawValue >= 0) {
    return rawValue;
  }
  return null;
}
~~~

Hàm trên là **minh họa nguyên tắc tránh chuyển mơ hồ**, chưa phải bộ xử lý tiền tệ cho mọi giao dịch. Nó không nhận chuỗi âm, số thập phân, giá trị vượt miền số nguyên an toàn của JavaScript, và **không biết đơn vị tiền**. Giá trị null ở đây có nghĩa “chưa tự chuẩn hóa được”, không có nghĩa tổng tiền bằng 0.

Nếu cần chuyển chuỗi có dấu thập phân chính xác sang **cents**, nên dùng thư viện decimal hoặc xử lý chuỗi theo quy tắc đã xác nhận, tránh nhân số thực nhị phân rồi làm tròn tùy tiện. Với giá trị rất lớn, có thể dùng Decimal128 hoặc kiểu số nguyên phù hợp trong database; cần thống nhất giữa Java, JavaScript, API và storage.

### Dùng $convert để quan sát những giá trị không thể chuyển

MongoDB aggregation có **$convert** với **onError** và **onNull**, hữu ích để tạo báo cáo trước khi ghi dữ liệu:

~~~javascript
db.ordersRaw.aggregate([
  {
    $project: {
      rawTotal: "$total",
      rawType: { $type: "$total" },
      asLong: {
        $convert: {
          input: "$total",
          to: "long",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
~~~

Đây là **phép thử chuyển kiểu kỹ thuật**, không phải quyết định chuẩn hóa nghiệp vụ. Ví dụ $convert có thể chuyển/truncate một số dạng numeric tùy phép chuyển; việc kết quả là long **không chứng minh giá trị có đơn vị tiền đúng**, cũng không chứng minh cách làm tròn phù hợp.

Không nên chạy một phép **$convert** rồi cập nhật hàng loạt ngay khi chưa phân loại các giá trị thất bại và trường hợp chuyển “thành công” nhưng sai ý nghĩa.

## 11. Chuẩn hóa thời gian: không bỏ qua múi giờ và độ chính xác

Thời gian có thể tồn tại dưới dạng:

~~~text
2026-11-10T09:30:00Z      Có UTC rõ ràng
2026-11-10T09:30:00+07:00 Có offset rõ ràng
2026-11-10 09:30:00       Không có offset
10/11/2026 09:30         Có thể ngày/tháng/năm; không có offset
1794303000000             Số cần biết đơn vị: millis hay seconds?
ISODate(...)              BSON Date
~~~

Hai giá trị sau biểu diễn **cùng một thời điểm**:

~~~text
2026-11-10T09:30:00Z
2026-11-10T16:30:00+07:00
~~~

Nhưng chuỗi **"2026-11-10 09:30:00"** không cho biết đó là giờ Việt Nam hay UTC. Tự gắn hậu tố Z có thể tạo sai lệch mà không gây lỗi parse.

Quy tắc chuẩn hóa cần nói rõ:

1. Trường đích là **BSON Date** biểu diễn thời điểm tuyệt đối.
2. Từng nguồn cũ có **timezone và định dạng** nào; lấy bằng chứng từ version/locale/cấu hình nguồn.
3. Giá trị epoch đang ở **giây, mili giây hay nanô giây**.
4. Ngày lịch không có giờ có nghĩa là **ngày theo múi giờ nghiệp vụ**, không phải mặc định midnight UTC.
5. Xử lý giờ mùa hè (DST), giờ địa phương không tồn tại hoặc xuất hiện hai lần ở những khu vực có DST.
6. Trường hợp mơ hồ phải đưa sang **xử lý thủ công hoặc tra cứu nguồn gốc**, không tự suy đoán.

Một aggregation có thể thử chuyển:

~~~javascript
db.ordersRaw.aggregate([
  {
    $project: {
      rawCreatedAt: "$createdAt",
      originalType: { $type: "$createdAt" },
      candidateDate: {
        $convert: {
          input: "$createdAt",
          to: "date",
          onError: null,
          onNull: null
        }
      }
    }
  }
]);
~~~

Nếu chuỗi không có offset mà engine chấp nhận parse, **vẫn phải kiểm tra ngữ nghĩa timezone** trước khi coi đó là kết quả đúng. Với những định dạng cũ cụ thể, có thể dùng **$dateFromString** với format/timezone đã được chốt; không nên dựa vào suy đoán format tự động cho mọi nguồn.

## 12. Chuẩn hóa chuỗi, enum và định danh

### Chuỗi và khoảng trắng

Trường **email**, **name** hay **code** có thể chứa:

~~~text
"  An  "
"AN"
"An"
"An\u00a0"   (khoảng trắng không ngắt dòng)
~~~

Các biến thể có thể nhìn rất giống nhau trên UI nhưng khác byte. **Trim** và chuẩn hóa Unicode có thể phù hợp cho một số loại nhãn, nhưng **không được áp dụng tùy tiện cho mọi định danh**. Một số mã khách hàng có khoảng trắng hoặc phân biệt chữ hoa/chữ thường theo quy tắc bên ngoài.

Đối với username/email, cần xác định:

- Case-insensitive hay case-sensitive theo nghiệp vụ?
- Có xử lý Unicode normalization không, và theo chuẩn nào?
- Có được phép đổi giá trị gốc đã được dùng làm khóa tham chiếu không?
- Có tồn tại hai record sẽ trở thành **trùng khóa** sau khi chuyển đổi không?
- Nếu phát hiện collision, ai có thẩm quyền quyết định gộp hay đổi định danh?

### Định danh khác kiểu

Một collection có thể chứa **customerId** kiểu String ở document này, ObjectId ở document khác. Trước khi đổi:

1. Kiểm kê cả hai kiểu.
2. Xác định nguồn chính **customers** dùng loại ID nào.
3. Kiểm tra xem chuỗi ký tự có phải biểu diễn cùng một ObjectId thật hay là một mã nghiệp vụ độc lập.
4. Kiểm tra các reference ở orders, payments, cache và analytics.
5. Có mapping table khi phải đổi ID và duy trì liên kết lịch sử.

**Đừng tự động ép mọi chuỗi 24 ký tự hexa thành ObjectId**: chuỗi đó có thể là business ID trông giống ObjectId nhưng không cùng danh tính.

## 13. Object, array và cấu trúc lồng nhau

Hai dạng dữ liệu:

~~~javascript
// Dạng cũ: một mặt hàng là object đơn
{ _id: "a", items: { sku: "BOOK-01", quantity: 1 } }

// Dạng mới: items là mảng
{ _id: "b", items: [{ sku: "BOOK-01", quantity: 1 }] }
~~~

Nếu nghiệp vụ định nghĩa **items luôn là danh sách**, có thể chuyển object đơn thành mảng **một phần tử**. Nhưng còn những trường hợp:

~~~javascript
{ _id: "c", items: null }
{ _id: "d" }
{ _id: "e", items: [] }
{ _id: "f", items: "BOOK-01" }
~~~

Chúng không cùng nghĩa:

- **null:** trường tồn tại nhưng không có giá trị; nguyên nhân cần xác minh.
- **missing:** phiên bản cũ chưa bao giờ ghi trường.
- **[]:** danh sách rỗng có chủ đích hoặc dữ liệu chưa được điền.
- **string:** có thể là SKU hoặc lỗi import, không tự biến thành dòng hàng đầy đủ.

Một phép chuyển đổi hợp lệ phải xác định **đầu vào được hỗ trợ**, **đầu ra**, và **xử lý ngoại lệ**. Ví dụ chỉ cho phép object chứa đủ **sku** và **quantity** chuyển thành array; mọi dạng khác được đánh dấu để điều tra.

Với nested object, cần lưu ý **thay toàn bộ object** có thể xóa các trường mới mà writer khác vừa thêm. Khi backfill, nên dùng update có điều kiện hoặc cập nhật chính xác field đích, tránh ghi đè toàn bộ document đã thay đổi kể từ lúc đọc.

## 14. Cùng kiểu chưa chắc cùng ý nghĩa

Đây là loại drift khó phát hiện hơn lỗi kiểu.

Giả sử tất cả record đều có:

~~~javascript
{ total: 120000 }
~~~

Nhưng:

- Writer A ghi **total = tổng trước thuế**.
- Writer B ghi **total = tổng sau thuế**.
- Writer C ghi **total = số tiền thanh toán thực nhận sau voucher**.

Không có một biểu thức **$type** nào phân biệt được ba ý nghĩa này. Chỉ có **hợp đồng nghiệp vụ, lịch sử triển khai, sourceSystem, chứng từ và đối soát** mới giúp xác định.

Do đó kế hoạch schema cần phân biệt:

**Chuẩn hóa biểu diễn:** đổi kiểu string sang integer, đổi tên field, dùng BSON Date.

**Chuẩn hóa ngữ nghĩa:** xác định một trường có nghĩa gì, thuộc đơn vị nào, được tính theo công thức nào và trạng thái nào là hợp lệ.

Nếu chỉ sửa biểu diễn nhưng không sửa sự không đồng nhất về ngữ nghĩa, hệ thống có thể có schema đẹp hơn nhưng báo cáo vẫn sai.

## 15. Xác định quy tắc chuyển đổi dưới dạng bảng quyết định

Trước khi chạy job, cần một **mapping specification** có thể review:

| Nhóm đầu vào | Điều kiện chứng minh | Thao tác | Kết quả |
|---|---|---|---|
| totalMinor kiểu long/int, currency hợp lệ | Đã đúng hợp đồng | Giữ nguyên | **UNCHANGED** |
| total là chuỗi chỉ có chữ số | Nguồn xác nhận là đơn vị nhỏ nhất và trong miền số an toàn | Chuyển sang totalMinor | **NORMALIZED** |
| total là chuỗi có dấu phân cách | Có quy tắc locale chắc chắn theo nguồn | Dùng parser theo locale đã xác minh | **NORMALIZED hoặc REVIEW** |
| total = null hoặc không tồn tại | Không có nguồn xác nhận số tiền | Không đặt mặc định 0 | **REVIEW** |
| status = paid | Từ điển nghiệp vụ xác nhận tương đương PAID | Map sang PAID | **NORMALIZED** |
| status = completed | Không rõ đã thanh toán hay đã giao | Không tự đoán | **REVIEW** |
| createdAt có offset ISO hợp lệ | Thể hiện thời điểm tuyệt đối | Chuyển sang BSON Date | **NORMALIZED** |
| createdAt không có timezone | Biết timezone của writer ở đúng giai đoạn | Parse theo quy tắc nguồn | **NORMALIZED hoặc REVIEW** |
| customer nhúng dạng {id: ...} | ID tra được chính xác theo tenant | Ghi customerId | **NORMALIZED** |
| customerId không tra được | Có khả năng orphan reference | Giữ lại để tra cứu | **REVIEW/QUARANTINE** |
| schemaVersion=2 nhưng dữ liệu vi phạm | Bản ghi mới sai hợp đồng | Điều tra writer và sửa có kiểm soát | **INVALID** |

**REVIEW** không đồng nghĩa **xóa dữ liệu**. Các bản mơ hồ thường cần giữ nguyên raw để xác định sau. Với dữ liệu tài chính hoặc pháp lý, việc ghi 0/UNKNOWN tùy tiện có thể làm thay đổi ý nghĩa chứng từ.

Một kế hoạch tốt nêu rõ **ai phê duyệt mapping**, **quy tắc áp dụng cho tenant/giai đoạn nào**, **cách ghi lại trường nguồn** và **điều kiện dừng job nếu tỷ lệ bất thường tăng**.

## 16. Chọn chiến lược chuẩn hóa: sửa tại chỗ hay dựng bộ dữ liệu mới?

Có hai chiến lược chính, mỗi cách có đánh đổi.

### 16.1. Backfill tại chỗ (in-place)

Mỗi document cũ được bổ sung field chuẩn rồi đánh dấu phiên bản mới. Ưu điểm là giữ nguyên ID và đường đọc hiện tại, không phải chuyển toàn bộ quan hệ sang collection mới. Hạn chế là job có thể cạnh tranh với writer live và khó rollback khi đã xóa field cũ.

Phù hợp khi dữ liệu không quá lớn, quy tắc có thể chạy idempotent, và có thể triển khai **expand → migrate → contract** mà không làm gián đoạn ứng dụng.

### 16.2. Dựng collection/bảng mới (side-by-side)

Tạo **orders_v2** từ **orders_raw**, bảo toàn khóa liên kết và tạo bảng mapping nếu ID đổi. Writer mới ghi theo hợp đồng mới; một pipeline chuyển dữ liệu cũ và đồng bộ thay đổi trong giai đoạn chuyển tiếp.

Ưu điểm là dễ so sánh hai bản và chuyển đọc có kiểm soát. Hạn chế là chi phí lưu trữ, index, replication, CDC, đồng bộ hai nguồn và chuyển đổi các tham chiếu lớn hơn.

| Khía cạnh | In-place | Side-by-side |
|---|---|---|
| Giữ ID và nơi truy vấn | Thuận lợi | Cần chuyển đường đọc hoặc alias |
| Dung lượng trong migration | Thường tăng ít hơn | Thêm tập dữ liệu mới và index |
| Rollback | Khó nếu xóa field cũ sớm | Có thể chuyển đọc lại trong thời gian còn đồng bộ |
| Cạnh tranh với writer | Cần bảo vệ update tại chỗ | Cần bảo vệ luồng delta giữa hai tập |
| Kiểm chứng old/new | Dựa trên field/version hoặc backup | So sánh hai collection rõ ràng |
| Thay cấu trúc lớn | Có thể khó | Thường phù hợp hơn nếu schema thay đổi sâu |

Không có lựa chọn luôn đúng. Đặc biệt, **side-by-side cũng có nguy cơ dữ liệu cũ ghi đè dữ liệu mới** nếu consumer hoặc backfill xử lý sai thứ tự, nên phải quản lý version/checkpoint.

## 17. Mẫu kế hoạch expand → migrate → contract

Một kế hoạch triển khai không gián đoạn thường có ba pha:

~~~mermaid
flowchart TD
    A["Khảo sát + hợp đồng schema v2"] --> B["EXPAND: ứng dụng đọc được v1 và v2"]
    B --> C["Sửa mọi writer để ghi v2 đúng"]
    C --> D["MIGRATE: backfill v1 theo batch"]
    D --> E["Theo dõi errors, lag, version và đối soát"]
    E --> F{"Đủ điều kiện chốt?"}
    F -->|"Chưa"| G["Sửa mapping, chạy lại an toàn"]
    G --> D
    F -->|"Đạt"| H["CONTRACT: chuyển read sang v2-only"]
    H --> I["Bật validation nghiêm, ngừng field cũ"]
    I --> J["Xóa field cũ theo chính sách và cửa sổ rollback"]
~~~

### EXPAND: tương thích trong giai đoạn có dữ liệu hỗn hợp

Ứng dụng phiên bản mới được phép đọc cả hai kiểu:

~~~javascript
function readOrderTotalMinor(order) {
  if (Number.isSafeInteger(order.totalMinor)) {
    return order.totalMinor;
  }

  if (typeof order.total === "string" &&
      /^[0-9]+$/.test(order.total)) {
    const parsed = Number(order.total);
    if (Number.isSafeInteger(parsed)) return parsed;
  }

  throw new Error("ORDER_TOTAL_REQUIRES_NORMALIZATION");
}
~~~

Đây chỉ là ví dụ cho phạm vi **VND integer trong miền an toàn** sau khi nghiệp vụ đã xác nhận quy tắc; các trường hợp USD/decimal phải có converter khác.

Trong pha này, **writer mới phải ghi v2 đúng**, đồng thời **ngăn writer cũ tiếp tục tạo v1** hoặc có lộ trình vô hiệu hóa/sửa chúng. Nếu phải chạy song song mobile client cũ, một API server chung nên chuyển dữ liệu đầu vào sang v2 trước khi ghi.

### MIGRATE: chuyển dữ liệu cũ

Backfill đọc v1, chạy converter theo mapping, lưu v2. Mỗi record cần được phân loại:

~~~text
ALREADY_VALID
NORMALIZED
NEEDS_REVIEW
INVALID_SOURCE
WRITE_CONFLICT_RETRY
FAILED_TECHNICAL
~~~

Không nên gộp tất cả thành một con số **“đã xử lý”**. Một document được đọc nhưng không chuyển vì thiếu thông tin không phải một document đã chuẩn hóa.

### CONTRACT: chỉ cho phép schema mới

Chỉ sau khi đã xác nhận không còn writer v1, read path v2 hoạt động đúng, các ngoại lệ được xử lý và khả năng rollback được xét, mới dừng đọc field cũ và bật validation nghiêm cho các thao tác tương lai. Việc xóa field cũ có thể cần lùi sau thêm một khoảng an toàn để không mất dữ liệu dùng cho điều tra.

## 18. Converter phải có tính quyết định và không được làm mất dữ liệu

Một converter tốt có dạng hàm thuần về logic:

\[
\text{normalize}(\text{raw},\ \text{mappingVersion})
\rightarrow \text{Normalized} \mid \text{NeedsReview}
\]

Nó phải dùng quy tắc đã công bố và cho kết quả có thể lặp lại. Ví dụ JavaScript minh họa trong **mongosh**, chỉ xử lý một tập trường hợp an toàn:

~~~javascript
const statusMapping = new Map([
  ["paid", "PAID"],
  ["PAID", "PAID"],
  ["pending", "PENDING"],
  ["PENDING", "PENDING"]
]);

function normalizeForMigration(raw) {
  const reasons = [];

  if (!raw || typeof raw !== "object") {
    return { kind: "NEEDS_REVIEW", reasons: ["INVALID_DOCUMENT"] };
  }

  const currency = raw.currency;
  if (currency !== "VND") {
    reasons.push("CURRENCY_NOT_COVERED_BY_THIS_RULE");
  }

  const status = statusMapping.get(raw.status);
  if (!status) {
    reasons.push("STATUS_UNKNOWN");
  }

  let totalMinor = null;
  if (typeof raw.total === "string" &&
      /^[0-9]+$/.test(raw.total)) {
    const parsed = Number(raw.total);
    if (Number.isSafeInteger(parsed)) totalMinor = parsed;
  }
  if (totalMinor === null) {
    reasons.push("TOTAL_UNSAFE_OR_AMBIGUOUS");
  }

  let createdAt = null;
  if (typeof raw.createdAt === "string" &&
      /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(raw.createdAt)) {
    const parsed = new Date(raw.createdAt);
    if (!Number.isNaN(parsed.getTime())) {
      createdAt = parsed;
    }
  }
  if (createdAt === null) {
    reasons.push("CREATED_AT_UNSAFE_OR_AMBIGUOUS");
  }

  if (typeof raw.customerId !== "string" ||
      raw.customerId.length === 0) {
    reasons.push("CUSTOMER_ID_MISSING");
  }

  if (reasons.length > 0) {
    return { kind: "NEEDS_REVIEW", reasons };
  }

  return {
    kind: "NORMALIZED",
    fields: {
      totalMinor: NumberLong(String(totalMinor)),
      currency: "VND",
      status,
      createdAt,
      customerId: raw.customerId,
      schemaVersion: 2
    }
  };
}
~~~

Đoạn mã cố tình **không** xử lý:

- Chuỗi số có dấu phân cách hoặc số thập phân.
- Date có offset khác Z, epoch, định dạng ngày/tháng hoặc giờ địa phương.
- Tổng tiền USD và currency thiếu.
- Customer chỉ có trong object nhúng.
- Record v2 hoặc các biến thể không được định nghĩa.

Hạn chế này **là ưu điểm của converter an toàn**, vì nó không đoán bừa các trường hợp chưa có quy tắc. Converter trong thực tế còn cần kiểm tra min/max, mapping tenant, timezone, precision và bất biến orderTotal từ items theo hợp đồng.

## 19. Dry run trước khi ghi bất kỳ document nào

Trước khi backfill, chạy converter ở chế độ **đọc và thống kê**, không update:

~~~javascript
const stats = {
  NORMALIZED: 0,
  NEEDS_REVIEW: 0
};
const reviewExamples = [];

db.ordersRaw.find({ schemaVersion: { $ne: 2 } }).forEach(raw => {
  const outcome = normalizeForMigration(raw);
  stats[outcome.kind] += 1;

  if (outcome.kind === "NEEDS_REVIEW" &&
      reviewExamples.length < 20) {
    reviewExamples.push({
      id: raw._id,
      reasons: outcome.reasons
    });
  }
});

printjson(stats);
printjson(reviewExamples);
~~~

Với tập dữ liệu lớn, không nên giữ toàn bộ document hoặc mọi lỗi trong RAM. Cần ghi **metrics tổng hợp**, **mẫu lỗi có giới hạn** và **checkpoint** theo batch. Nếu phải rà soát dữ liệu cá nhân, log không nên chứa thông tin nhạy cảm không cần thiết; có thể ghi ID và mã lỗi thay vì payload đầy đủ.

Kết quả dry run cần được phân tích theo **tenant**, **sourceSystem**, **phiên bản writer** và **thời kỳ**. Tỷ lệ chuyển đổi thấp thường báo hiệu mapping chưa đủ hoặc chưa hiểu dữ liệu, không phải lý do để tự động nới quy tắc parser.

Đầu ra có thể được trình bày:

| Loại kết quả | Số lượng minh họa | Hành động |
|---|---:|---|
| Đã đúng v2 | 700.000 | Không ghi lại |
| Tự chuyển an toàn | 240.000 | Đưa vào backfill |
| Cần xác minh timezone | 30.000 | Tra cứu nguồn và quy tắc |
| Currency hoặc đơn vị mơ hồ | 18.000 | Đối soát nghiệp vụ |
| Reference không tìm thấy | 8.000 | Điều tra dữ liệu liên kết |
| Lỗi kiểu/giá trị lạ | 4.000 | Quarantine và xử lý có phê duyệt |

Các con số chỉ minh họa cách phân loại. Tổng số record và số record được xử lý thật phải đến từ phép đo của hệ thống.

## 20. Backfill có checkpoint, idempotency và chống ghi đè dữ liệu mới

Giả sử worker đọc một order v1, chuẩn bị chuyển nó thành v2. Trong khoảng ấy, API có thể cập nhật status. Nếu worker ghi lại cả document cũ, nó có thể **đè mất trạng thái mới**.

Thiết kế phù hợp cần:

1. **Ghi theo batch có giới hạn**, tránh update toàn bộ hàng triệu record trong một lệnh kéo dài.
2. **Dùng phiên bản hoặc dấu hiệu cạnh tranh** khi update, để không ghi đè document đã thay đổi sau lúc đọc.
3. **Chỉ ghi các trường được converter xác nhận**, không replace nguyên document.
4. **Đặt schemaVersion sau khi các trường chuẩn cần thiết đã được ghi cùng thao tác phù hợp**.
5. **Checkpoint** để tiếp tục sau lỗi; không coi một record đã đọc là đã xử lý thành công.
6. **Cho phép chạy lại (idempotent)**: document đã ở v2 phải được bỏ qua hoặc xác nhận không thay đổi.
7. **Giới hạn tốc độ** để không làm ảnh hưởng workload production.

Ví dụ minh họa cho một record có **revision** được writer duy trì:

~~~javascript
const raw = db.ordersRaw.findOne({ _id: "r1" });
const outcome = normalizeForMigration(raw);

if (outcome.kind === "NORMALIZED") {
  const result = db.ordersRaw.updateOne(
    {
      _id: raw._id,
      schemaVersion: { $ne: 2 },
      revision: raw.revision
    },
    {
      $set: outcome.fields,
      $inc: { revision: 1 }
    }
  );

  if (result.modifiedCount !== 1) {
    print("Có khả năng xung đột; phải đọc lại, không ghi đè");
  }
}
~~~

**Điều kiện tiên quyết quan trọng:** ví dụ chỉ an toàn khi mọi writer có thể làm thay đổi các trường liên quan đều quản lý **revision** nhất quán, và một revision chưa có giá trị không được dùng như bằng chứng chống concurrency. Trong dữ liệu legacy chưa có revision, cần triển khai cơ chế version hoặc phối hợp ghi khác trước khi dựa vào ví dụ này.

Trong môi trường nhiều writer chưa có version, một phương án khác là chuyển đổi tại collection mới có log thay đổi và reconcile theo thứ tự, hoặc đặt cửa sổ kiểm soát writer/transaction theo mức nhất quán cần. **Không nên tùy tiện thêm điều kiện schemaVersion rồi coi như đủ chống lost update.**

### Đánh dấu thành công đúng lúc

Một checkpoint chỉ nên tiến sau khi những ghi thuộc phạm vi batch đã được xác nhận theo cơ chế đáng tin. Nếu job crash sau commit nhưng trước checkpoint, chạy lại phải nhận ra record đã ở v2 và không tạo tác dụng phụ trùng.

Nếu converter dùng dữ liệu bên ngoài như bảng tỷ giá hoặc hồ sơ khách, phải cố định **phiên bản nguồn tham chiếu** để cùng một record không cho kết quả khác giữa hai lần chạy chỉ vì bảng tham chiếu đã đổi.

## 21. Thiết lập schema validation ở giai đoạn phù hợp

MongoDB hỗ trợ **JSON Schema validation** đối với document ghi vào collection. Ví dụ tạo collection đích mới:

~~~javascript
db.createCollection("ordersV2", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: [
        "tenantId",
        "customerId",
        "totalMinor",
        "currency",
        "status",
        "createdAt",
        "schemaVersion"
      ],
      properties: {
        tenantId: { bsonType: "string" },
        customerId: { bsonType: "string" },
        totalMinor: {
          bsonType: ["int", "long"],
          minimum: 0
        },
        currency: { enum: ["VND"] },
        status: { enum: ["PENDING", "PAID", "CANCELLED"] },
        createdAt: { bsonType: "date" },
        schemaVersion: { enum: [2] }
      }
    }
  },
  validationAction: "error"
});
~~~

Đây là validator **thu hẹp cho bài toán VND minh họa**, không phải schema đa tiền tệ đầy đủ. Ví dụ cũng chưa kiểm tra **items**, **tính đúng của tổng tiền**, **customer thuộc tenant** hoặc mọi cạnh hợp lệ của state machine. Các bất biến đó phải được bảo vệ bằng cơ chế thích hợp.

Nếu bật validator nghiêm trên collection có hàng triệu document v1, các thao tác update lên document cũ có thể bị từ chối vì kết quả vẫn không thỏa schema mới. Vì vậy nên triển khai theo giai đoạn:

- Ưu tiên **sửa writer mới** để không tạo thêm document sai.
- Dùng collection mới hoặc thiết lập validation phù hợp với giai đoạn chuyển tiếp.
- Dọn và đối soát dữ liệu v1.
- **Siết validation** khi đã sẵn sàng, không phá những đường cập nhật còn phụ thuộc v1.

Schema validation là **hàng rào chống drift mới**, không tự khắc phục các document đã tồn tại và không thay thế logic kiểm tra nghiệp vụ.

## 22. SchemaVersion và compatibility của hệ nhiều phiên bản

Trong hệ có nhiều dịch vụ/mobile app, có thể tồn tại đồng thời:

~~~text
Writer v1   -> ghi total là string
Writer v2   -> ghi totalMinor là long
Reader v1   -> chỉ hiểu total
Reader v2   -> hiểu cả total và totalMinor
Analytics   -> đọc định kỳ toàn collection
CDC worker  -> phát sự kiện từ thay đổi document
~~~

Nếu cập nhật writer v2 trước khi có reader tương thích, reader v1 có thể không đọc được dữ liệu mới. Nếu reader v2 đã xuất xưởng nhưng writer v1 còn ghi dài hạn, schema drift tiếp tục tích lũy.

Một lộ trình:

1. **Inventory writers/readers** đang đọc/ghi collection và các schema cụ thể.
2. Triển khai **reader tương thích**, có xử lý rõ ràng cho record chưa chuyển.
3. Đổi tất cả **writer phía server** sang hợp đồng v2; kiểm soát client cũ qua API chuyển đổi.
4. Backfill và quan sát tỷ lệ v2.
5. Xác nhận analytics/CDC/read models hiểu schema mới.
6. Chuyển sang **v2-only** khi không còn phụ thuộc v1.
7. Sau cửa sổ rollback, loại bỏ field cũ theo chính sách.

Không được coi trường **schemaVersion: 2** tự chứng minh document đúng: importer có thể ghi giá trị 2 nhưng vẫn lưu **totalMinor: "120000"**. Cần kiểm tra kiểu và các bất biến độc lập với version.

## 23. Lặp dữ liệu, cache và các read model trong quá trình chuẩn hóa

Trong NoSQL, một record nguồn có thể đã được nhân sang nhiều nơi:

~~~text
orders (nguồn chính)
   |
   +--> recent_orders_by_customer
   +--> sales_dashboard
   +--> search_index
   +--> Redis order-cache
   +--> analytics warehouse
   +--> archives/backups
~~~

Nếu chỉ chuẩn hóa **orders** nhưng dashboard vẫn đọc trường **total** dạng string từ pipeline cũ, kết quả có thể tiếp tục sai.

Kế hoạch chuyển đổi nên liệt kê:

- **Canonical source**: nơi quyết định ý nghĩa và phiên bản.
- **Dữ liệu dẫn xuất**: trường nào được tính/sao chép từ nguồn, có thể dựng lại không.
- **Change feed/outbox/CDC**: event payload có schema version nào, consumer nào đang xử lý.
- **Cache**: có TTL hoặc invalidation/rebuild nào.
- **Analytics**: báo cáo trước/sau migration có cần tái tính không.
- **Archive/backup**: dữ liệu lịch sử không nên bị sửa nếu có yêu cầu chứng từ; phải có quy tắc đọc/khôi phục phiên bản cũ.

**Đừng đồng bộ dữ liệu lịch sử như thể nó là cache.** Ví dụ **unitPriceAtPurchase** trong hóa đơn phải giữ đúng giá đã chốt, còn **product.currentPrice** là giá hiện tại. Chuẩn hóa biểu diễn hai trường không cho phép ghi đè giá lịch sử bằng giá mới.

## 24. Đối chiếu với các hệ NoSQL khác

### DynamoDB: item có kiểu attribute

DynamoDB hỗ trợ attribute kiểu String, Number, Binary, Map, List, Set, Boolean, Null và những kiểu liên quan. Trong cùng một table, item cũ có thể chứa **amount** dạng String, item mới dùng **amountMinor** dạng Number.

Ứng dụng cần:

- Kiểm kê phân bố attribute/type bằng quét có kiểm soát hoặc pipeline phân tích phù hợp.
- Xác định canonical attribute names và types.
- Sửa writer để ghi kiểu đúng.
- Backfill có **condition expressions** hoặc version check, tránh ghi đè item đã thay đổi.
- Đo read/write capacity, pagination, throttling và chi phí backfill.
- Xem lại GSI/read model vì field đổi kiểu/tên có thể ảnh hưởng query theo index.

Một **FilterExpression** trên Scan không tự biến thao tác thành truy vấn nhẹ; dữ liệu vẫn có thể được đọc rộng trước khi lọc. Với bảng lớn, có thể cân nhắc export/analytics rồi xử lý theo batch thay vì Scan production không giới hạn.

### Redis: cùng key pattern nhưng value có format khác

Ví dụ:

~~~text
profile:user-01 -> JSON String v1
profile:user-02 -> JSON String v2
profile:user-03 -> Redis Hash
~~~

Ứng dụng cũ dùng **GET** cho cả ba key sẽ lỗi **WRONGTYPE** với Hash. Trước khi chuẩn hóa, kiểm kê **TYPE**, key namespace, TTL và serializer, sau đó chọn chiến lược:

- Giữ một kiểu value thống nhất theo key namespace.
- Chuyển từng key có version/điều kiện phù hợp.
- Dùng tên key mới như **profile:v2:{userId}** để side-by-side khi cần.
- Kiểm soát TTL và cache miss; dữ liệu cache có thể đơn giản hơn bằng cách invalidate rồi dựng lại từ nguồn.

Quét key toàn hệ thống bằng lệnh nặng có thể ảnh hưởng vận hành. Với Redis, nên dùng cơ chế scan theo batch và giới hạn tốc độ, không mặc định mọi key phải được đọc ở một lệnh.

### Cassandra: bảng có schema nhưng payload vẫn có thể drift

Cassandra CQL có schema cột rõ hơn so với document linh hoạt; một cột khai báo **int** không chấp nhận chuỗi bất kỳ như document JSON. Nhưng dữ liệu vẫn có thể không đồng nhất về **ngữ nghĩa**, ví dụ:

- Một cột lưu **cents** ở service A, **đồng** ở service B.
- Event payload dạng text/JSON có các phiên bản không tương thích.
- Enum dạng text khác chữ hoa/chữ thường.
- Hai access tables nhân bản cùng dữ liệu nhưng update không đồng bộ.
- Các cột mới null trên phần lớn dữ liệu lịch sử.

Kế hoạch có thể gồm bảng v2 theo access patterns mới, writer tương thích, backfill với paging/checkpoint và xử lý timestamp/tombstones. Không nên tự suy rằng batch nhiều partition có giao dịch ACID tương đương một transaction quan hệ.

### Document database khác

Các hệ document có cách validation/index/transaction khác nhau. Cần đọc khả năng cụ thể của sản phẩm thay vì sao chép lệnh MongoDB. Nhưng quy trình chung **profile → contract → classify → migrate → validate → monitor** vẫn áp dụng.

## 25. Thay đổi unique key và nguy cơ trùng sau chuẩn hóa

Giả sử user ID trước đây lưu:

~~~text
"User-07"
"user-07"
" user-07 "
~~~

Sau khi trim/lowercase, cả ba trở thành **user-07**. Nếu chúng đại diện ba người khác nhau, một migration tự gộp sẽ làm mất dữ liệu. Nếu chúng là cùng một người, vẫn phải giải quyết các reference, quyền, lịch sử và bản ghi liên quan.

Trước khi tạo unique index trên khóa chuẩn:

1. Tính **candidate normalized key** trong tập khảo sát.
2. Nhóm theo candidate để tìm **collision**.
3. Đối chiếu các thực thể với nghiệp vụ và nguồn bên ngoài.
4. Chọn quy tắc merge/rename/reject có người chịu trách nhiệm.
5. Sửa các reference và bản sao liên quan một cách có kiểm soát.
6. Chỉ tạo unique index khi dữ liệu đã đáp ứng điều kiện.

Một unique index tạo trên dữ liệu đã trùng sẽ bị từ chối. Đó là **tín hiệu dữ liệu cần giải quyết**, không phải lý do bỏ unique constraint hoặc âm thầm xóa một record cho index tạo thành công.

Với hệ đa tenant, cần xem uniqueness là **toàn cục hay theo tenant**. Nếu hai tenant được phép cùng dùng mã khách hàng **customer-07**, unique key có thể cần bao gồm tenantId.

## 26. Bảo vệ dữ liệu trong quá trình migration

Khi migration xử lý dữ liệu thật, phải xác định an toàn dữ liệu ở ít nhất bốn mức:

**Tính toàn vẹn:** không làm mất field không liên quan, không đổi timestamp sai timezone, không chuyển null thành 0 tùy tiện, không ghi đè update mới, không sửa snapshot lịch sử sai mục đích.

**Tính sẵn sàng:** batch size/concurrency, retry/backoff, ảnh hưởng lên index, replication, disk I/O, cache và p95/p99 của API production.

**Bảo mật/phân quyền:** job có quyền vừa đủ; không log dữ liệu cá nhân hoặc payload bí mật không cần thiết; đảm bảo tenant scope khi dò reference hoặc dựng lại bản sao.

**Khả năng khôi phục:** checkpoint, backup đã kiểm chứng, cách chuyển reader về phiên bản cũ, khả năng replay và tài liệu mô tả những thay đổi không thể đảo ngược.

Đừng viết:

~~~javascript
// Phản ví dụ: nguy hiểm trên dữ liệu chưa phân loại.
// db.ordersRaw.updateMany({}, { $set: { currency: "VND" } });
~~~

Lệnh như vậy có thể làm sai mọi đơn USD. Cũng không nên mặc định **updateMany** với converter tổng quát sẽ không đụng bản ghi đã chuẩn hoặc writer mới vừa cập nhật.

Khi bắt buộc xóa field cũ, nên thực hiện **sau thời hạn tương thích/rollback** và sau khi xác minh tất cả reader, analytics, exporter và consumer đã không còn phụ thuộc. Backfill có thể đảo ngược về mặt kỹ thuật nhưng **không phải mọi phép đổi ngữ nghĩa đều có thể khôi phục** nếu giá trị gốc đã mất.

## 27. Đo chất lượng trước, trong và sau chuẩn hóa

Một kế hoạch thành công cần có các chỉ số:

| Chỉ số | Diễn giải | Tại sao quan trọng |
|---|---|---|
| **Coverage** | Phần trăm document đủ các field bắt buộc | Biết phạm vi còn thiếu |
| **Type conformity** | Tỷ lệ có đúng kiểu BSON/attribute | Theo dõi drift kiểu |
| **Semantic validity** | Tỷ lệ thỏa enum, đơn vị, công thức nghiệp vụ | Tránh “đúng kiểu nhưng sai nghĩa” |
| **Normalization success rate** | Số record chuyển được / số record cần chuyển | Tiến độ thực |
| **Review/quarantine rate** | Tỷ lệ không đủ bằng chứng chuyển tự động | Theo dõi chất lượng nguồn |
| **Writer drift rate** | Số record mới sinh ra sai schema trên mỗi đơn vị thời gian | Xác nhận đã sửa tận gốc |
| **Write conflict/retry rate** | Xung đột khi backfill gặp writer live | Điều chỉnh concurrency |
| **Backfill lag** | Khoảng thời gian/khối lượng giữa dữ liệu gốc và v2 | Theo dõi đuổi kịp nguồn |
| **Reference mismatch** | Số ID không thể join đúng nguồn | Phát hiện orphan và sai tenant |
| **Business reconciliation** | Sai lệch tổng tiền, số đơn, trạng thái trước/sau | Kiểm chứng không đổi ý nghĩa |
| **Query latency** | p95/p99 của đường đọc quan trọng | Bảo đảm migration không làm hỏng SLO |
| **Error rate sau rollout** | Lỗi parse/validation/reader fallback | Phát hiện trường hợp chưa được mô hình hóa |

Một dashboard có thể hiển thị:

~~~text
orders_total                   1,000,000
orders_schema_v2_valid           930,000
orders_v1_auto_normalizable       45,000
orders_needs_review              25,000

new_invalid_writes_per_hour            0
normalization_write_conflict_rate     0.4%
read_fallback_v1_rate                2.1%
projection_lag_p95                   8 s
~~~

Các giá trị chỉ minh họa. Điều quan trọng là **mẫu số của từng metric phải được xác định**. “93% dữ liệu v2” không đồng nghĩa “93% dữ liệu hợp lệ” nếu có v2 sai schema, và “2,1% reader fallback” phụ thuộc phân bố traffic chứ không phải tỷ lệ record v1.

## 28. Đối soát bằng bất biến nghiệp vụ, không chỉ đếm số record

Sau migration, hai tập dữ liệu có thể có cùng số document mà vẫn sai nghiêm trọng:

~~~text
Trước migration:
  100 orders, tổng doanh thu hợp lệ = 8.000.000 VND

Sau migration:
  100 orders, nhưng một số đơn đã bị chia/multiply đơn vị tiền
  -> tổng doanh thu đọc ra = 800.000.000 VND
~~~

Vì vậy, cần các phép đối soát:

1. **Số lượng bản ghi** theo tenant, tháng và trạng thái.
2. **Tổng tiền/đơn vị** theo đúng currency và công thức hợp đồng.
3. **Số cặp tham chiếu hợp lệ**, orphan và collision.
4. **Min/max thời gian** và số đơn theo cửa sổ UTC/ngày địa phương.
5. **Phân bố status trước và sau** theo mapping có phê duyệt.
6. **Bất biến từng order**: tổng bằng các dòng hàng chốt theo quy tắc.
7. **Ảnh hưởng read model**: số liệu dashboard/search/cache có khớp nguồn trong độ trễ cho phép?

Khi đối soát tài chính, không nên cộng lẫn nhiều currency hoặc dùng float sai precision. Nếu cần chuyển đổi tỷ giá, phải định nghĩa **tỷ giá tại thời điểm nào và nguồn nào**, thay vì lấy tỷ giá hiện tại để “sửa” lịch sử.

## 29. Lập kế hoạch thực thi theo các giai đoạn

Một kế hoạch triển khai có thể được viết dưới dạng bảng:

| Giai đoạn | Công việc | Điều kiện chuyển sang bước sau |
|---|---|---|
| **A — Khảo sát** | Kiểm kê kiểu, field, enum, tenant, writer, các bản sao | Có báo cáo baseline và danh sách biến thể |
| **B — Thiết kế** | Hợp đồng schema v2, mapping, ngoại lệ, bất biến | Nghiệp vụ và chủ sở hữu dữ liệu phê duyệt |
| **C — Chặn drift mới** | Reader tương thích, writer v2, validation đầu vào | Dữ liệu mới đúng schema, metric drift giảm về ngưỡng mục tiêu |
| **D — Dry run** | Converter chỉ đọc, đo auto/review/error | Không có lỗi diễn giải phổ biến, chi phí phù hợp |
| **E — Pilot** | Backfill một tenant hoặc một tập nhỏ có giới hạn | Đối soát dữ liệu và SLO đạt |
| **F — Backfill** | Batch theo checkpoint, retry, CAS/version, giới hạn tải | Tỷ lệ v2 hợp lệ đạt tiêu chí, lỗi mơ hồ được ghi nhận |
| **G — Shadow/read switch** | So old/new, canary traffic | Tính đúng và độ trễ đạt mức yêu cầu |
| **H — Contract** | Bật validation nghiêm, ngừng fallback, ngừng field cũ | Tất cả writer/consumer tương thích, cửa sổ rollback được xử lý |
| **I — Vận hành** | Alert schema drift, job đối soát, tài liệu runbook | Có owner và quy trình xử lý dữ liệu bất thường mới |

**Tiêu chí dừng (stop conditions)** nên được ghi rõ, ví dụ:

- Tỷ lệ record **NEEDS_REVIEW** vượt mức đã phê duyệt trong batch.
- Xuất hiện sai lệch tổng tiền hoặc số đơn không giải thích được.
- Tăng mạnh p95/p99 latency hoặc lỗi timeout.
- Số **write conflicts** tăng cao làm ảnh hưởng writer live.
- CDC lag vượt phạm vi còn có thể backfill an toàn.
- Phát hiện mapping không đúng cho một tenant/nguồn cụ thể.

Khi gặp stop condition, ưu tiên **dừng ghi tiếp**, giữ checkpoint và bằng chứng, phân tích nguyên nhân; không tự nới quy tắc validation để có số liệu tiến độ đẹp hơn.

## 30. Ví dụ quyết định cho dữ liệu ngày không rõ múi giờ

Giả sử một triệu đơn có createdAt dạng:

~~~text
"2026-11-10 09:30:00"
~~~

Có ba nguồn:

| Nguồn | Thông tin có thể xác minh | Cách xử lý |
|---|---|---|
| Mobile app A, trước 2025 | Có tài liệu xác nhận ghi giờ Asia/Ho_Chi_Minh | Parse theo timezone đó cho đúng phạm vi |
| Payment API B | Có hợp đồng xác nhận thời gian UTC | Parse theo UTC |
| File import C | Không có metadata về múi giờ | Không tự chuyển; cần tra nguồn/chứng từ |

Nếu parser mặc định UTC cho cả ba, dữ liệu từ mobile A sẽ bị lệch bảy giờ. Điều này có thể chuyển một đơn qua **ngày báo cáo khác**, làm sai thống kê giờ cao điểm, doanh thu ngày và các điều kiện thời hạn hoàn tiền.

Quy tắc tốt có dạng:

~~~yaml
# Đặc tả minh họa cho pipeline, không phải cấu hình chạy tự động
mappingVersion: "orders-time-v2"
rules:
  - sourceSystem: "mobile-a"
    period: "before-2025-01-01"
    inputFormat: "yyyy-MM-dd HH:mm:ss"
    timezone: "Asia/Ho_Chi_Minh"
    output: "BSON Date UTC instant"
  - sourceSystem: "payment-b"
    inputFormat: "yyyy-MM-dd HH:mm:ss"
    timezone: "UTC"
    output: "BSON Date UTC instant"
  - sourceSystem: "import-c"
    decision: "NEEDS_REVIEW"
~~~

Mục tiêu là lưu **một thời điểm đúng** trong field đích, chứ không đơn giản gắn hậu tố Z. Khi thay timezone hoặc quy tắc ở một nguồn, phải version mapping và biết những record đã chuyển theo phiên bản nào để có thể kiểm chứng/điều chỉnh nếu cần.

## 31. Những nhầm lẫn dễ gặp

| Nhầm lẫn | Vì sao nguy hiểm | Cách xử lý đúng |
|---|---|---|
| “NoSQL không có schema” | Ứng dụng vẫn kỳ vọng trường, kiểu và ngữ nghĩa cụ thể | Xây hợp đồng schema và validation phù hợp |
| “$type giống nhau nghĩa là dữ liệu đúng” | Số có thể khác đơn vị, string có thể khác enum | Kiểm tra ngữ nghĩa và bất biến |
| “Dùng $toInt cho mọi chuỗi là xong” | Chuỗi mơ hồ, quá miền, decimal hoặc sai currency | Phân loại trước; chuyển theo quy tắc nguồn |
| “createdAt là string thì cứ thêm Z” | Có thể sai timezone hàng giờ | Xác minh nguồn và timezone |
| “Null và missing đều coi là 0” | Có thể tạo doanh thu hoặc số lượng giả | Giữ trạng thái không biết/cần review |
| “ToUpperCase đủ chuẩn enum” | COMPLETED và PAID có thể khác nghiệp vụ | Mapping theo state machine |
| “SchemaVersion=2 chứng minh hợp lệ” | Writer/importer có thể gắn version sai | Validation độc lập kiểu và giá trị |
| “Backfill updateMany luôn an toàn” | Có thể ghi đè writer live hoặc đổi sai record | Batch, version check, retry và checkpoint |
| “Cập nhật source là mọi nơi đã chuẩn” | Cache/analytics/read model có thể giữ schema cũ | Lập inventory bản sao và consumers |
| “Tạo unique index sẽ tự giải quyết record trùng” | Tạo index thất bại nếu dữ liệu trùng; không biết nên gộp ai | Phát hiện collision, xử lý nghiệp vụ |
| “Đếm số record bằng nhau nghĩa là migration đúng” | Tổng tiền, ngày và liên kết vẫn có thể sai | Đối soát invariant và phân bố |
| “Không cần fix writer, cứ chạy migration hằng ngày” | Dữ liệu sai tiếp tục sinh ra và chi phí kéo dài | Chặn drift mới trước/sớm trong backfill |
| “Dữ liệu mơ hồ thì xóa cho sạch” | Mất lịch sử/chứng từ và khả năng điều tra | Quarantine, giữ nguồn và quyết định có phê duyệt |
| “Đã bật validator thì dữ liệu cũ tự đúng” | Validation chỉ tác động vào ghi theo cấu hình | Backfill/đối soát riêng |

## 32. Quy trình thực hành có thể tái sử dụng

~~~mermaid
flowchart TD
    A["Tập dữ liệu NoSQL thực tế"] --> B["Khảo sát: fields, types, enums, time, IDs"]
    B --> C["Phân loại biến thể theo tenant/writer/time"]
    C --> D["Hợp đồng schema v2 + bất biến"]
    D --> E["Mapping có bằng chứng + ngoại lệ"]
    E --> F["Reader tương thích + writer ghi đúng v2"]
    F --> G["Dry run / pilot"]
    G --> H{"Kết quả tự chuyển đủ an toàn?"}
    H -->|"Không"| I["Review, bổ sung quy tắc có phê duyệt"]
    I --> E
    H -->|"Có"| J["Backfill batch + checkpoint + CAS/version"]
    J --> K["Đối soát schema, dữ liệu, báo cáo"]
    K --> L{"Sai lệch hoặc lỗi?"}
    L -->|"Có"| M["Dừng, giữ bằng chứng, sửa và chạy lại"]
    M --> G
    L -->|"Không"| N["Canary read v2 + contract"]
    N --> O["Giám sát schema drift mới"]
~~~

Để triển khai một dự án tương tự, hãy chuẩn bị:

1. **Danh sách collection/table/key namespace** và những dịch vụ có quyền ghi/đọc.
2. **Bộ metric baseline** về kiểu, field missing, null, enum, đơn vị, format, duplicate IDs, tỷ lệ sai bất biến.
3. **Hợp đồng schema đích**, người chịu trách nhiệm dữ liệu và chính sách với record mơ hồ.
4. **Bản đặc tả converter có version**, phân tách rõ tự chuyển và cần review.
5. **Kế hoạch tương thích writer/reader**, tránh schema v1 tiếp tục xuất hiện.
6. **Dry run/pilot**, giới hạn batch/concurrency và điều kiện dừng.
7. **Checkpoint, idempotency và cơ chế chống ghi đè writer live**.
8. **Đối soát số lượng và ý nghĩa nghiệp vụ**, không chỉ tỷ lệ chuyển kiểu.
9. **Quy trình xử lý cache/read model/analytics/backup** liên quan.
10. **Runbook rollback, theo dõi lâu dài** và cảnh báo schema drift trở lại.

## 33. Bài tập thực hành

### Bài tập 1 — Tìm các biến thể

Một collection lưu các document:

~~~javascript
{ _id: "a", amount: "150000", status: "paid" }
{ _id: "b", amount: 150000, status: "PAID" }
{ _id: "c", amount: "150.000", status: "completed" }
{ _id: "d", amount: null }
{ _id: "e", status: "PAID" }
~~~

Hãy phân loại **missing**, **null**, **string**, **number**, các enum và trường hợp mơ hồ. Viết MongoDB aggregation đếm số record theo kiểu amount và một truy vấn tìm record thiếu amount.

### Bài tập 2 — Chọn schema đích

Thiết kế schema đơn hàng với **totalMinor, currency, createdAt, status, customerId, schemaVersion**. Nêu kiểu dữ liệu đích, các trường bắt buộc, bất biến nghiệp vụ và điều kiện nào không thể kiểm tra chỉ bằng BSON type.

### Bài tập 3 — Giải thích dữ liệu thời gian

Ba writer ghi:

~~~text
Writer A: "2026-11-14 09:00:00" (Asia/Ho_Chi_Minh)
Writer B: "2026-11-14T09:00:00Z"
Writer C: 1794646800000 (có tài liệu là Unix milliseconds)
~~~

Hãy đưa về thời điểm tuyệt đối, chỉ ra điều gì phải biết trước khi parse và cách kiểm chứng không chuyển nhầm ngày báo cáo. Nếu một writer không có tài liệu timezone, nêu chính sách xử lý.

### Bài tập 4 — Đơn vị tiền

Hệ có **amount = 125.50** cho đơn USD và **amount = 125500** cho đơn VND. Hãy giải thích vì sao không thể lấy cả hai làm totalMinor chỉ bằng ép int. Đề xuất cách lưu số tiền, currency và quy tắc chuyển đổi theo từng nguồn.

### Bài tập 5 — Chuyển cấu trúc mảng

Một số bản ghi có **items** là object, số khác là array, null hoặc missing. Hãy định nghĩa trường hợp nào được tự chuyển thành array một phần tử, trường hợp nào cần review và cách tránh mất field khi backfill.

### Bài tập 6 — Writer cũ còn hoạt động

API mới ghi **schemaVersion=2** nhưng một batch job cũ tiếp tục ghi **total** dạng string. Hãy vạch lộ trình expand → migrate → contract, xác định cần sửa writer nào, khi nào bật validation nghiêm và điều kiện nào cho phép ngừng hỗ trợ v1.

### Bài tập 7 — Concurrent update

Worker đọc order có **status=PENDING**, chuẩn bị chuyển schema. Trong lúc đó webhook cập nhật **status=PAID**. Hãy mô tả lỗi xảy ra nếu worker replace toàn document, và thiết kế update có điều kiện/version để không ghi đè trạng thái mới.

### Bài tập 8 — Collision khi chuẩn hóa ID

Ba customer IDs là **"User-07"**, **"user-07"**, **" user-07 "**. Hãy tính candidate normalized ID, tìm collision, giải thích vì sao không được tự gộp ba bản ghi và những tham chiếu nào cần kiểm tra trước khi tạo unique index.

### Bài tập 9 — Backfill và đo tiến độ

Một collection có 3 triệu document; 2,4 triệu đã đúng v2, 400.000 có thể chuyển an toàn, 150.000 cần xem timezone và 50.000 có currency không rõ. Hãy thiết kế metric, checkpoint, batch, stop conditions và phương án xử lý 200.000 record cần review.

### Bài tập 10 — Source và read model

Đơn hàng đã chuyển totalMinor sang long, nhưng dashboard và Redis cache vẫn đọc **total** dạng string. Hãy thiết kế lộ trình cập nhật consumer, invalidate/rebuild cache, đối soát dashboard và cách xử lý event v1 phát lại sau migration.

### Bài tập 11 — Validation không thay thế nghiệp vụ

Một validator yêu cầu **totalMinor là long** và **status thuộc enum**. Hãy nêu ít nhất năm loại dữ liệu sai vẫn có thể vượt validator, như sai currency, sai công thức tổng, tham chiếu khách không tồn tại hoặc sai tenant. Đề xuất tầng nào chịu trách nhiệm bảo vệ từng bất biến.

### Bài tập 12 — Kế hoạch triển khai an toàn

Viết một kế hoạch migration cho bộ dữ liệu có 100 triệu record đang được ghi liên tục. Tối thiểu phải có **baseline**, **mapping version**, **pilot**, **throttling**, **CAS/version**, **checkpoint**, **dry run**, **rollback**, **business reconciliation**, **monitoring** và **chuyển đổi reader/consumer**. Mô tả điều kiện nào buộc job dừng thay vì tiếp tục làm dữ liệu sai.

---

**Kết luận:** Schema linh hoạt cho phép NoSQL lưu những biến thể mới mà không cần thay đổi cấu trúc tập trung mỗi lần triển khai, nhưng sự linh hoạt ấy không xóa nhu cầu **hợp đồng dữ liệu**. Để phát hiện và chuẩn hóa dữ liệu không đồng nhất, phải làm đúng thứ tự: **khảo sát dữ liệu thật → xác định biến thể và ý nghĩa → thiết kế schema đích → lập mapping có bằng chứng → chặn writer tạo drift mới → dry run → backfill idempotent có kiểm soát → đối soát bất biến → siết validation và giám sát lâu dài**. Mục tiêu không phải chỉ là làm mọi document trông giống nhau, mà là bảo toàn **ý nghĩa nghiệp vụ, khả năng truy vấn và tính đúng đắn** trong suốt quá trình thay đổi.
