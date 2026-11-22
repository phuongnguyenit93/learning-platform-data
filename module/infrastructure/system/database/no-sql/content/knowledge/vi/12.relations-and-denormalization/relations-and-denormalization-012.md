# Đối chiếu mô hình hạn chế lặp dữ liệu với mô hình tối ưu đường truy cập

Trong thiết kế NoSQL, hai mục tiêu thường kéo dữ liệu theo hai hướng khác nhau:

1. **Hạn chế lặp dữ liệu:** mỗi thông tin nghiệp vụ có một nơi sở hữu chính; những nơi khác lưu khóa tham chiếu rồi truy vấn hoặc ghép khi cần. Cách làm này giảm số bản phải sửa khi thông tin thay đổi.
2. **Tối ưu đường truy cập:** tổ chức dữ liệu theo đúng những gì một API hoặc màn hình cần đọc, thậm chí lưu lại một số trường ở nhiều bản ghi, nhiều bảng hoặc nhiều key để truy vấn nhanh và ít phải ghép.

Không có quy tắc “luôn hạn chế lặp” hoặc “NoSQL thì phải lặp dữ liệu”. Nếu chỉ quan tâm tránh lặp, một trang có thể phải đọc và ghép quá nhiều nguồn. Nếu chỉ quan tâm tốc độ đọc, một lần đổi dữ liệu gốc có thể buộc cập nhật hàng nghìn bản sao, khiến kết quả cũ và mới cùng tồn tại. Điều cần thiết là xác định **nguồn sự thật**, **đường đọc/ghi thực tế**, **bất biến nghiệp vụ**, **độ trễ đồng bộ được phép** và **chi phí vận hành**.

Bài học dùng ví dụ **danh sách sản phẩm trên sàn thương mại** với MongoDB để đối chiếu hai mô hình; sau đó mở rộng sang Redis, Cassandra và những bài toán có dữ liệu lịch sử. Những con số trong ví dụ là giả định học tập, không phải benchmark hay cấu hình mặc định áp dụng cho mọi hệ.

## 1. Trước hết phải hiểu “lặp dữ liệu” là gì

Xét một sản phẩm được bán bởi một người bán. Trang danh sách cần hiển thị:

~~~text
productId          p-42
title              Sổ tay A5
priceMinor         80000
currency           VND
sellerDisplayName  Văn phòng phẩm An
availability       IN_STOCK
~~~

Có hai cách:

**Mô hình hạn chế lặp** lưu thông tin sản phẩm trong **products**, tên người bán trong **sellers**, tồn kho trong **inventory**. Document sản phẩm chỉ lưu **sellerId** để tham chiếu. Một lần đổi tên người bán được ghi ở một nơi.

**Mô hình phục vụ đường đọc** lưu thêm document **product_cards** chứa sẵn cả tên người bán và trạng thái còn hàng. API danh sách sản phẩm chỉ cần đọc tập này, nhưng phải có cơ chế cập nhật bản sao khi **sellers** hoặc **inventory** thay đổi.

~~~mermaid
flowchart LR
    subgraph Canonical["Dữ liệu nguồn"]
      P["products"]
      S["sellers"]
      I["inventory"]
    end
    P -->|"sellerId"| S
    P -->|"productId"| I
    P --> V["product_cards: read model"]
    S --> V
    I --> V
    V --> A["API danh sách sản phẩm"]
~~~

**Một dữ liệu xuất hiện ở nhiều nơi chưa chắc là sai.** Nó có thể là:

- **Bản sao dẫn xuất (derived copy):** tên người bán hiện tại được nhân sang thẻ sản phẩm để đọc nhanh, phải đồng bộ khi tên đổi.
- **Cache:** giá trị có thể hết hạn hoặc được dựng lại từ nguồn chính, thường đi kèm TTL/invalidation.
- **Snapshot lịch sử:** đơn giá tại thời điểm mua được lưu trong hóa đơn; **không** cập nhật theo giá catalog mới.
- **Đối tượng được dùng chung:** hồ sơ người bán có danh tính và vòng đời riêng, không nên biến mỗi bản sao thành một nguồn chính cạnh tranh.

Một bước bắt buộc là gắn **ngữ nghĩa** cho dữ liệu lặp: nó phải giống dữ liệu gốc ở hiện tại, được phép trễ, hay phải giữ nguyên một trạng thái trong quá khứ?

## 2. Hai hướng thiết kế và những gì mỗi hướng tối ưu

| Tiêu chí | Hạn chế lặp dữ liệu (nguồn riêng + tham chiếu) | Tối ưu đường truy cập (phi chuẩn hóa/read model) |
|---|---|---|
| **Nơi cập nhật dữ liệu gốc** | Thường tập trung vào một thực thể sở hữu | Vẫn nên có nguồn chính; bản sao cần đồng bộ |
| **Truy vấn đọc một trang tổng hợp** | Có thể cần join, batch reads hoặc nhiều round-trip | Có thể lấy một document/item đã dựng sẵn |
| **Thay đổi một thông tin dùng chung** | Sửa một nơi rồi các lần đọc nguồn chính thấy giá trị mới theo ngữ nghĩa nhất quán | Có thể phải cập nhật hàng loạt bản sao |
| **Dung lượng** | Thường ít bản sao cùng trường hơn | Có thêm dữ liệu nhân bản, index, checkpoint |
| **Chi phí ghi** | Ghi vào nguồn có thẩm quyền | Có write amplification vì phải cập nhật read model |
| **Độ mới của dữ liệu hiển thị** | Phụ thuộc cách đọc, cache, replica và consistency | Phụ thuộc đồng bộ tức thì hay bất đồng bộ |
| **Truy vấn theo chiều mới** | Có thể phải thêm index/lookup | Có thể phải tạo read model khác |
| **Đọc/ghi trong cùng một ranh giới nhất quán** | Dễ giữ một thực thể nguồn rõ ràng | Cần phân biệt bất biến nguồn với bản sao phục vụ đọc |
| **Xóa/đổi quyền** | Ít bản sao nghiệp vụ phải dò hơn | Phải tìm và xử lý cả bản sao, cache, archive |
| **Độ phức tạp hệ thống** | Phức tạp ở đường đọc và phép ghép | Phức tạp ở pipeline đồng bộ, lỗi một phần và vận hành |

Tên gọi **“chuẩn hóa” (normalization)** thường được dùng để mô tả giảm lặp dữ liệu; **“phi chuẩn hóa” (denormalization)** mô tả sao chép hay tổ chức lại thông tin cho mục tiêu truy cập. Trong NoSQL, đây là **phổ lựa chọn**, không phải chỉ có hai trạng thái loại trừ lẫn nhau.

Ví dụ, một document order có thể nhúng các dòng hàng của chính nó (hợp lý vì cùng giao dịch), đồng thời tham chiếu customerId (khách có danh tính riêng), rồi xuất thêm một read model danh sách đơn. Cả ba kỹ thuật có thể tồn tại cùng lúc.

## 3. Bắt đầu bằng access patterns, không bắt đầu bằng số collection

Giả sử một sàn bán văn phòng phẩm có những yêu cầu:

1. Khách chọn danh mục **stationery**, xem **20 sản phẩm mới cập nhật gần nhất**, kèm tên người bán, giá hiện tại và nhãn còn/hết hàng.
2. Khách mở chi tiết sản phẩm theo **productId**; phải thấy nội dung catalog và thông tin người bán.
3. Người bán đổi **displayName**; trang danh sách cần cập nhật trong thời gian chấp nhận được.
4. Hệ kho thay đổi **availableStock** liên tục khi đơn được đặt hoặc hủy.
5. Khi checkout, hệ thống **phải kiểm tra lại giá và tồn kho ở nguồn có thẩm quyền**, không được quyết định thu tiền chỉ dựa trên thẻ sản phẩm đã cache.
6. Quản trị viên có thể tạm ngừng một sản phẩm; sản phẩm bị ngừng không được hiển thị trong đường truy cập công khai theo hợp đồng.

Bảng yêu cầu đọc/ghi:

| Thao tác | Điều kiện đầu vào | Kết quả cần có | Độ mới/nguyên tử |
|---|---|---|---|
| List category | tenantId, categoryId, cursor | 20 thẻ sản phẩm đã sắp xếp | Ví dụ chấp nhận tên người bán trễ tối đa 30 giây |
| Product detail | tenantId, productId | Catalog + seller + availability | Dữ liệu sản phẩm đủ mới theo yêu cầu chi tiết |
| Rename seller | tenantId, sellerId | Đổi tên đúng một người bán | Nguồn **sellers** phải đúng sau thao tác ghi thành công |
| Change price | tenantId, productId | Giá hiện tại hợp lệ | Checkout phải xác nhận giá mới nhất theo hợp đồng |
| Reserve stock | tenantId, productId, quantity | Không giữ quá số lượng được phép | Điều kiện tồn kho phải được bảo vệ tại ghi |
| Unpublish | tenantId, productId | Không nhận bán sản phẩm đã ngừng | Không dựa hoàn toàn vào bản sao trễ |

Ví dụ về độ trễ **30 giây** chỉ là hợp đồng giả định. Nếu nghiệp vụ yêu cầu “ẩn ngay tức thì khi unpublish”, một read model bất đồng bộ không thể tự bảo đảm điều đó nếu API không kiểm tra thêm trạng thái nguồn hoặc cơ chế thu hồi có hiệu lực ngay.

Vì vậy, **có thể chấp nhận trễ tên người bán nhưng không chấp nhận dùng tồn kho cũ để xác nhận bán**. Không nên gộp mọi trường vào một mức nhất quán duy nhất.

## 4. Mô hình hạn chế lặp: nguồn riêng và các khóa tham chiếu

Trong MongoDB, một mô hình có thể gồm:

~~~javascript
// products: sản phẩm có danh tính độc lập
{
  _id: "p-42",
  tenantId: "shop-a",
  sellerId: "seller-7",
  categoryIds: ["stationery", "office"],
  title: "Sổ tay A5",
  priceMinor: 80000,
  currency: "VND",
  published: true,
  updatedAt: ISODate("2026-11-14T09:00:00Z")
}

// sellers: một người bán có thể sở hữu nhiều sản phẩm
{
  _id: "seller-7",
  tenantId: "shop-a",
  displayName: "Văn phòng phẩm An",
  version: 3
}

// inventory: nguồn trạng thái tồn của sản phẩm
{
  _id: "p-42",
  tenantId: "shop-a",
  availableStock: 18
}
~~~

Các document trên là **mô hình minh họa**; nếu áp dụng vào môi trường thực tế cần quy ước ID, phân quyền, validation và các index đúng workload.

Lợi ích:

- **sellers.displayName** được quản lý ở một document.
- **products.priceMinor** có một nguồn giá hiện tại.
- **inventory.availableStock** có một nơi kiểm soát thao tác giảm tồn.
- Catalog, người bán và tồn kho có **vòng đời và tần suất cập nhật riêng**.
- Muốn sửa hồ sơ người bán, không phải ghi lại toàn bộ product documents.

Nhược điểm là API cần lấy nhiều thực thể. Nếu đọc từng sản phẩm rồi chạy từng truy vấn riêng để lấy tên seller và stock, màn hình danh sách dễ gặp **N+1 queries**.

### Truy vấn đọc nguồn theo hai pha

Đầu tiên lấy 20 sản phẩm phù hợp:

~~~javascript
db.products.createIndex({
  tenantId: 1,
  categoryIds: 1,
  published: 1,
  updatedAt: -1,
  _id: -1
});

const productsPage = db.products.find(
  {
    tenantId: "shop-a",
    categoryIds: "stationery",
    published: true
  },
  {
    _id: 1,
    sellerId: 1,
    title: 1,
    priceMinor: 1,
    currency: 1,
    updatedAt: 1
  }
)
.sort({ updatedAt: -1, _id: -1 })
.limit(20)
.toArray();
~~~

**categoryIds** là mảng, nên index trên nó là **multikey index**. Đây chỉ là **index ứng viên**: việc sort có được index phục vụ hiệu quả hay không phụ thuộc điều kiện truy vấn, quy tắc multikey và query plan của MongoDB. Cần dùng **explain("executionStats")** trên dữ liệu đại diện, không suy từ việc đã gọi createIndex là chắc chắn tránh mọi bước sort.

Sau đó gom sellerId và productId của **chính trang 20 sản phẩm** để lấy dữ liệu tham chiếu:

~~~javascript
const sellerIds = [...new Set(productsPage.map(p => p.sellerId))];
const productIds = productsPage.map(p => p._id);

const sellerRows = db.sellers.find(
  { _id: { $in: sellerIds }, tenantId: "shop-a" },
  { _id: 1, displayName: 1 }
).toArray();

const inventoryRows = db.inventory.find(
  { _id: { $in: productIds }, tenantId: "shop-a" },
  { _id: 1, availableStock: 1 }
).toArray();

const sellersById = new Map(sellerRows.map(s => [s._id, s]));
const stockByProduct = new Map(inventoryRows.map(i => [i._id, i]));

const cards = productsPage.map(p => ({
  productId: p._id,
  title: p.title,
  priceMinor: p.priceMinor,
  currency: p.currency,
  sellerDisplayName: sellersById.get(p.sellerId)?.displayName ?? null,
  availability: (stockByProduct.get(p._id)?.availableStock ?? 0) > 0
    ? "IN_STOCK"
    : "UNKNOWN_OR_OUT_OF_STOCK"
}));
~~~

Đây là ví dụ dành cho **mongosh** có JavaScript hiện đại. **UNKNOWN_OR_OUT_OF_STOCK** cố ý phân biệt trường hợp không có inventory row với kết luận chắc chắn còn hàng; trong ứng dụng thật cần chốt cách xử lý missing references.

Với trang có 20 sản phẩm, cách hai pha có thể biến nhiều lần truy cập lặp thành **một lần đọc products, một lần đọc sellers theo tập ID và một lần đọc inventory theo tập ID**. Nó vẫn có chi phí ghép, nhưng tránh suy luận sai rằng mô hình tham chiếu nhất thiết phải gây 20–40 network round trips.

## 5. Có thể ghép ngay tại MongoDB bằng $lookup

Với cùng dữ liệu, MongoDB aggregation có thể ghép các thông tin cần thiết:

~~~javascript
db.products.aggregate([
  {
    $match: {
      tenantId: "shop-a",
      categoryIds: "stationery",
      published: true
    }
  },
  { $sort: { updatedAt: -1, _id: -1 } },
  { $limit: 20 },
  {
    $lookup: {
      from: "sellers",
      let: { sellerRef: "$sellerId", tenantRef: "$tenantId" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$sellerRef"] },
                { $eq: ["$tenantId", "$$tenantRef"] }
              ]
            }
          }
        },
        { $project: { _id: 1, displayName: 1 } }
      ],
      as: "seller"
    }
  },
  {
    $lookup: {
      from: "inventory",
      let: { productRef: "$_id", tenantRef: "$tenantId" },
      pipeline: [
        {
          $match: {
            $expr: {
              $and: [
                { $eq: ["$_id", "$$productRef"] },
                { $eq: ["$tenantId", "$$tenantRef"] }
              ]
            }
          }
        },
        { $project: { _id: 1, availableStock: 1 } }
      ],
      as: "stock"
    }
  },
  {
    $project: {
      _id: 0,
      productId: "$_id",
      title: 1,
      priceMinor: 1,
      currency: 1,
      sellerDisplayName: { $arrayElemAt: ["$seller.displayName", 0] },
      availableStock: { $arrayElemAt: ["$stock.availableStock", 0] }
    }
  }
]);
~~~

Đặt **$match → $sort → $limit trước $lookup** có ý nghĩa khi sản phẩm được lựa chọn và xếp hạng hoàn toàn dựa trên dữ liệu của **products**. Ta chỉ ghép seller/inventory cho những sản phẩm thực sự nằm trong trang.

Tuy nhiên, nếu yêu cầu chuyển thành **“lọc những sản phẩm còn hàng, rồi lấy 20 sản phẩm mới nhất trong số đó”**, việc limit 20 trước khi kiểm tra stock sẽ làm thiếu hoặc sai kết quả. Khi ấy phải thay đổi truy vấn hoặc có một read model/index phản ánh điều kiện availability trước lúc giới hạn. **Thứ tự stage là một phần của ngữ nghĩa**, không chỉ mẹo hiệu năng.

MongoDB hỗ trợ $lookup, nhưng không có nghĩa phép join trên tập cực lớn luôn rẻ. Độ chọn lọc, index, kích thước dữ liệu, phân bố tenant và số collection tham gia vẫn ảnh hưởng thời gian chạy.

## 6. Mô hình tối ưu đường truy cập: tạo thẻ sản phẩm đọc sẵn

Giả sử đo đạc cho thấy trang danh sách danh mục nhận lưu lượng rất cao, còn tên người bán hiếm khi đổi. Một read model riêng có thể phù hợp:

~~~javascript
// product_cards: bản đọc dẫn xuất, không phải nguồn giá/tồn duy nhất
{
  _id: "p-42",
  tenantId: "shop-a",
  categoryIds: ["stationery", "office"],
  title: "Sổ tay A5",
  priceMinor: 80000,
  currency: "VND",
  published: true,
  sellerId: "seller-7",
  sellerDisplayName: "Văn phòng phẩm An",
  sellerVersion: 3,
  availability: "IN_STOCK",
  updatedAt: ISODate("2026-11-14T09:00:00Z"),
  projectionUpdatedAt: ISODate("2026-11-14T09:00:02Z")
}
~~~

API có thể chỉ đọc một collection:

~~~javascript
db.product_cards.find(
  {
    tenantId: "shop-a",
    categoryIds: "stationery",
    published: true
  },
  {
    title: 1,
    priceMinor: 1,
    currency: 1,
    sellerDisplayName: 1,
    availability: 1,
    updatedAt: 1
  }
)
.sort({ updatedAt: -1, _id: -1 })
.limit(20);
~~~

Điều này có thể giảm lượng công việc ghép khi phục vụ một trang, vì một read model chứa các trường đã chuẩn bị. Nhưng vẫn cần index phù hợp và đo query plan. **Phi chuẩn hóa không tự tạo hiệu năng tốt nếu đường lọc/sort không được hỗ trợ.**

### Nguồn sự thật của từng trường phải minh bạch

| Trường trong product_cards | Nguồn chính | Mức độ được phép trễ trong ví dụ |
|---|---|---|
| title, priceMinor, currency | products | Theo hợp đồng danh sách; checkout kiểm tra lại |
| published | products | Nếu bắt buộc ẩn ngay, cần cơ chế đọc/thu hồi đảm bảo điều đó |
| sellerDisplayName | sellers | Ví dụ tối đa 30 giây |
| availability | inventory | Chỉ là nhãn gợi ý, không xác nhận giao dịch |
| categoryIds | products | Đồng bộ khi sản phẩm đổi danh mục |
| sellerVersion | sellers | Dùng phát hiện bản cập nhật cũ và đối soát |
| projectionUpdatedAt | pipeline xây read model | Dùng quan sát tuổi bản sao, không thay thế version nguồn |

Người dùng không nên hiểu **IN_STOCK** trên thẻ là một reservation hợp lệ. Tồn khả dụng có thể thay đổi ngay sau khi hiển thị; bước checkout bắt buộc có conditional write hoặc quy trình reservation tại nguồn tồn kho.

## 7. Đọc nhanh phải đánh đổi bao nhiêu lần ghi?

Giả sử một người bán có **20.000 sản phẩm**. Khi đổi **displayName**:

**Mô hình hạn chế lặp:**

~~~text
UPDATE sellers["seller-7"].displayName
-> một thực thể nguồn thay đổi
-> trang đọc mới join tới nguồn chính theo mô hình nhất quán đã chọn
~~~

**Mô hình read model phi chuẩn hóa:**

~~~text
UPDATE sellers["seller-7"].displayName
-> phát sự kiện SellerRenamed
-> tìm product_cards của seller-7
-> cập nhật tối đa 20.000 thẻ sản phẩm liên quan
-> xác nhận đồng bộ / retry / đối soát
~~~

Con số **20.000** là số document **có thể cần cập nhật**, không có nghĩa luôn phải là 20.000 round-trip mạng. Database có thao tác hàng loạt; pipeline có thể xử lý batch hoặc dựng lại theo cách khác. Tuy nhiên, lượng dữ liệu ghi/index update và chi phí đồng bộ vẫn tồn tại.

Ta có thể mô tả gần đúng:

\[
\text{Write amplification}
\approx
\frac{\text{số thao tác/bản sao phải cập nhật}}{\text{số thực thể nguồn thay đổi}}
\]

Với một lần đổi tên người bán làm 20.000 product cards thay đổi, write amplification theo số bản ghi dẫn xuất có thể rất cao. Đây chỉ là phép mô tả ý niệm; số I/O vật lý còn phụ thuộc index, storage engine, batch và replication.

Ngược lại, nếu đọc danh sách sản phẩm rất nhiều lần mỗi giây, việc **ghép seller cho mỗi trang** cũng có chi phí. Đánh đổi đúng phải đặt cùng một thang đo:

- Số request đọc mỗi giây.
- Số sản phẩm hiển thị mỗi request.
- Số lần đổi tên/giá/tồn kho mỗi giây.
- Số bản sao chịu ảnh hưởng mỗi thay đổi.
- Thời gian CPU, disk I/O, network và độ trễ p95/p99.
- Độ mới tối đa được phép và khả năng hồi phục sau lỗi.

Không thể tuyên bố “lưu thêm sellerName luôn giúp nhanh” nếu chi phí fan-out khi đổi tên vượt lợi ích hoặc nếu hệ thống đã có caching/batch lookup hiệu quả.

## 8. Không phải trường nào cũng nên sao chép

Một quyết định tinh tế là **phi chuẩn hóa có chọn lọc** thay vì sao chép mọi thuộc tính.

| Trường | Đặc điểm | Hướng cân nhắc |
|---|---|---|
| Seller display name | Đổi hiếm, đọc nhiều | Bản sao trên product card có thể đáng giá |
| Price hiện tại | Đổi ít hoặc nhiều tùy ngành; ảnh hưởng giao dịch | Có thể hiển thị snapshot ngắn hạn, nhưng checkout phải xác minh nguồn |
| Available stock chính xác | Thay liên tục, bị nhiều order tác động | Không dùng bản sao trễ để bảo đảm không oversell |
| Availability badge | Có thể chấp nhận “còn hàng” mang tính gợi ý | Cache được nếu UI hiểu giới hạn |
| Product title | Đọc thường xuyên, cập nhật không nhiều | Có thể nhúng trong card cùng nguồn version |
| User password hash/secret | Nhạy cảm, đường đọc đặc biệt | Không sao chép vào read model public |
| Danh sách toàn bộ review | Tăng liên tục, có thể rất lớn | Lưu riêng, chỉ nhân bản aggregate như ratingCount nếu cần |
| Tổng số sao đánh giá | Dữ liệu dẫn xuất có thể cập nhật bằng sự kiện | Chỉ nên giữ nếu có quy tắc tính/đối soát |

“Phi chuẩn hóa toàn bộ đối tượng cho tiện” có thể làm rò rỉ trường nhạy cảm trong cache/index, khiến thay đổi cấu trúc khó khăn và tăng chi phí xóa dữ liệu cá nhân.

**Một read model nên chứa đúng các trường cần cho một hoặc một nhóm access pattern gần nhau**, không phải một bản copy vô điều kiện của mọi nguồn dữ liệu.

## 9. Đồng bộ dữ liệu lặp: tức thời hay bất đồng bộ?

Có hai hướng chính.

### 9.1. Cập nhật đồng bộ trong phạm vi có thể giao dịch

Khi ghi nguồn chính, ứng dụng cập nhật bản dẫn xuất trong cùng transaction nếu tất cả ghi thuộc phạm vi database hỗ trợ và bài toán thật sự cần ràng buộc ấy.

Ưu điểm là giảm cửa sổ nhìn thấy dữ liệu lệch giữa các bản ghi thuộc giao dịch. Đổi lại, transaction lớn hơn làm tăng lượng công việc ghi, tranh chấp, thời gian chờ và số trường hợp lỗi cần retry.

Nếu một lần đổi tên seller cần cập nhật 20.000 thẻ, không nên mặc định đó là một transaction khổng lồ. Cần đánh giá giới hạn, hiệu năng, quy mô fan-out và yêu cầu độ mới.

### 9.2. Cập nhật bất đồng bộ từ sự kiện thay đổi

Một mô hình phổ biến:

~~~mermaid
flowchart TD
    A["Lệnh đổi tên seller"] --> B["Cập nhật sellers nguồn chính"]
    B --> C["Ghi outbox/change event có version"]
    C --> D["Worker nhận SellerRenamed"]
    D --> E["Cập nhật product_cards liên quan theo batch"]
    E --> F["Đánh dấu checkpoint & đo lag"]
    E -->|"Lỗi"| G["Retry an toàn / dead-letter / đối soát"]
    G --> D
~~~

Ở mô hình này, đường ghi nguồn chính có thể thành công trước khi toàn bộ thẻ sản phẩm được cập nhật. Ta phải **định nghĩa cửa sổ sai lệch được phép** và cách giám sát nó.

Một sự kiện minh họa:

~~~json
{
  "eventId": "seller-7-version-4",
  "eventType": "SellerRenamed",
  "tenantId": "shop-a",
  "sellerId": "seller-7",
  "version": 4,
  "displayName": "An Stationery",
  "occurredAt": "2026-11-14T10:00:00Z"
}
~~~

**version** là số phiên bản đơn điệu của chính seller do nguồn tạo ra; consumer có thể dùng nó để từ chối áp dụng sự kiện cũ sau sự kiện mới. **eventId** giúp nhận diện lần phát lại. Hai khái niệm này khác nhau: một sự kiện có thể được giao nhiều lần nhưng version vẫn không đổi.

## 10. Chống dữ liệu quay ngược khi event đến sai thứ tự

Giả sử seller đổi tên hai lần:

~~~text
Version 4: "An Stationery"
Version 5: "An Office"

Thứ tự đến consumer:
  event version 5 tới trước
  event version 4 tới sau
~~~

Nếu consumer chỉ ghi đè **sellerDisplayName** mỗi khi thấy event, thẻ sản phẩm cuối cùng có thể quay về tên phiên bản 4.

Một update có điều kiện theo version:

~~~javascript
db.product_cards.updateMany(
  {
    tenantId: "shop-a",
    sellerId: "seller-7",
    $or: [
      { sellerVersion: { $lt: 5 } },
      { sellerVersion: { $exists: false } }
    ]
  },
  {
    $set: {
      sellerDisplayName: "An Office",
      sellerVersion: 5,
      projectionUpdatedAt: ISODate("2026-11-14T10:00:05Z")
    }
  }
);
~~~

Khi version 4 đến sau, consumer sử dụng filter tương đương **sellerVersion < 4**; bản ghi đã ở version 5 không bị hạ phiên bản. Đây là một phần của chiến lược chống event sai thứ tự.

Trong hệ thật còn phải xử lý:

- Cập nhật **sellers** trước khi phát sự kiện theo một cơ chế không làm mất event.
- Khi cùng seller có nhiều sản phẩm mới tạo trong lúc job fan-out đang chạy, thẻ mới phải nhận phiên bản phù hợp.
- Retry của batch cập nhật không được làm giảm version hoặc ghi đè bản mới.
- Nếu product đổi seller giữa lúc consumer xử lý, phải chặn event của seller cũ ghi sai product hiện tại.
- Nếu không có trường **sellerVersion** ở dữ liệu cũ, phải có backfill hoặc điều kiện cập nhật ban đầu.
- Nếu một bản sao bị bỏ sót hoàn toàn, phải có job đối soát hoặc dựng lại từ nguồn.

**UpdateMany thành công không chứng minh tất cả 20.000 thẻ đã được xử lý** nếu trong lúc chạy có sự kiện mới và tập dữ liệu biến động. Cần đọc kết quả sửa đổi, checkpoint, quy tắc quét lại và đối soát theo mục tiêu nghiệp vụ.

## 11. Chặn mất sự kiện khi cập nhật nguồn

Một lỗi kinh điển:

~~~text
1. UPDATE sellers thành công
2. Ứng dụng crash trước khi publish SellerRenamed
3. product_cards không nhận được cập nhật
~~~

Nếu phát event bằng một lệnh mạng độc lập sau commit, nguồn chính và bus sự kiện có thể lệch vĩnh viễn khi không có cơ chế khôi phục.

Các phương án:

**Transactional outbox:** ghi thay đổi seller và một bản ghi outbox trong cùng transaction của cơ sở dữ liệu khi phạm vi hỗ trợ. Worker đọc outbox, publish event, rồi đánh dấu trạng thái theo quy trình retry. Phía nhận vẫn cần idempotency vì event có thể được phát lại.

**Change data capture/change stream:** theo dõi thay đổi từ nguồn dữ liệu; cần hiểu retention của log thay đổi, resume token/checkpoint, khả năng bỏ lỡ khi ngắt quá lâu và backfill.

**Đối soát định kỳ:** so version/timestamp hoặc các thuộc tính then chốt giữa nguồn và read model, sửa bản thiếu/sai.

Không cần áp dụng tất cả giải pháp cùng lúc trong mọi hệ thống. Nhưng nếu read model được dùng để đưa ra quyết định quan trọng, phải có cách xử lý **sự kiện mất, trùng, sai thứ tự và consumer dừng giữa chừng**.

## 12. Hai lớp nhất quán: bất biến nguồn và độ mới bản đọc

Một hệ thống có thể áp dụng hai mức yêu cầu:

**Bất biến nguồn:** khi một khách đặt 4 sản phẩm, tồn kho không được bị trừ vượt lượng khả dụng. Ví dụ MongoDB conditional update:

~~~javascript
const requested = 4;

const stockResult = db.inventory.updateOne(
  {
    _id: "p-42",
    tenantId: "shop-a",
    availableStock: { $gte: requested }
  },
  { $inc: { availableStock: -requested } }
);

if (stockResult.modifiedCount !== 1) {
  print("Không thể giữ số lượng yêu cầu");
}
~~~

Điều kiện kiểm tra cùng thao tác cập nhật tránh tình huống hai client cùng đọc số tồn cũ rồi đều ghi giảm. Đoạn code chỉ minh họa một SKU; quy trình order nhiều SKU và payment cần thiết kế bất biến/transaction/reservation riêng.

**Độ mới bản đọc:** thẻ sản phẩm có thể vẫn hiện **IN_STOCK** thêm vài giây sau khi tồn kho hết. Nếu sản phẩm chấp nhận nhãn gợi ý như vậy, việc hiển thị trễ không cho phép checkout bán vượt tồn.

Nếu nghiệp vụ yêu cầu không hiển thị sản phẩm đã **unpublished** ngay khi thao tác hoàn tất, ta có thể chọn:

- Đọc/kiểm tra trạng thái nguồn trước khi hiển thị hoặc trước bước hành động quan trọng.
- Dùng invalidation/đường cập nhật đồng bộ có bảo đảm phù hợp.
- Không dùng read model bất đồng bộ làm nguồn duy nhất cho quyết định công khai nếu mức trễ không được phép.

**Sao chép dữ liệu để đọc nhanh không làm thay đổi quyền sở hữu bất biến.** Hệ thống vẫn phải biết ranh giới ghi nào quyết định giá hợp lệ, số lượng tồn hay quyền truy cập.

## 13. Dữ liệu lịch sử là một trường hợp lặp có chủ ý khác hẳn

Ví dụ đơn đã thanh toán:

~~~javascript
{
  _id: "order-900",
  tenantId: "shop-a",
  productId: "p-42",
  items: [
    {
      productId: "p-42",
      titleAtPurchase: "Sổ tay A5",
      unitPriceAtPurchase: 80000,
      quantity: 2
    }
  ],
  totalMinor: 160000,
  currency: "VND",
  status: "PAID"
}
~~~

Nếu giá catalog tăng từ **80.000** lên **90.000 VND**, thẻ sản phẩm hiện tại có thể đổi giá, nhưng **unitPriceAtPurchase** của order cũ **không được đồng bộ theo catalog**. Đây là snapshot của giao dịch, không phải cache bị stale.

Phân biệt:

| Loại bản sao | Mục tiêu | Khi nguồn chính thay đổi |
|---|---|---|
| **Snapshot lịch sử** | Giữ dữ kiện đã chốt | Không thay đổi theo nguồn hiện tại |
| **Cache** | Giảm độ trễ cho dữ liệu hiện tại | Hết hạn/invalidate/dựng lại |
| **Read model** | Sắp dữ liệu theo một truy vấn | Đồng bộ theo event/backfill và mức trễ cho phép |
| **Replica** | Tăng khả năng chịu lỗi/đọc theo khả năng database | Đồng bộ theo cơ chế replication của hệ |

Một **replica của database** không phải cùng khái niệm với **read model phi chuẩn hóa**. Replica thường nhân bản dữ liệu engine để phục vụ sẵn sàng/đọc; read model thay đổi **hình dạng dữ liệu** nhằm phục vụ truy vấn khác.

Nhầm lẫn snapshot với cache có thể phá hủy chứng từ và lịch sử giao dịch.

## 14. Khi truy vấn thay đổi, mô hình tối ưu cũng phải thay đổi

Giả sử ngày đầu tiên chỉ có trang “chi tiết sản phẩm theo productId”. Đọc một product, một seller và một inventory record có thể đủ nhanh.

Sau đó xuất hiện ba truy vấn:

1. **Danh sách theo danh mục:** 20 thẻ mới nhất mỗi lần.
2. **Tất cả sản phẩm của một seller:** phân trang theo updatedAt.
3. **Top sản phẩm bán chạy theo tuần:** tổng hợp số lượng order.

Ba đường truy cập này khác nhau:

~~~text
Get product by productId
  -> products + seller + stock

List products by category
  -> product_cards indexed by category + sort key

List products by seller
  -> products indexed by sellerId + sort key,
     hoặc read model riêng nếu cần

Top-selling by week
  -> sales_aggregates_by_week hoặc pipeline analytics
~~~

Không cần biến **product_cards** thành một bản ghi chứa mọi kiểu thống kê để cố dùng chung cho mọi màn hình. Một read model có giá trị khi nó phục vụ **một đường truy cập đủ quan trọng**, với chi phí đồng bộ có thể giải thích và kiểm soát.

### Chọn index hay tạo thêm read model?

Trước khi nhân bản dữ liệu, hãy xem:

- Query trên nguồn hiện có có thể dùng index, projection hoặc pagination tốt hơn không?
- Có thể gom các lần đọc reference theo batch để tránh N+1 không?
- Có thể dùng $lookup với tập dữ liệu được lọc/giới hạn trước không?
- Cache ngắn hạn trên key có giải quyết được phần lớn tải đọc không?
- Query thực sự cần sort/filter trên thuộc tính của nhiều thực thể hay không?
- Độ trễ, CPU, memory hoặc network nào đang là nút thắt dựa trên số liệu?

**Thêm index** cũng có write/storage cost, nhưng thường ít phức tạp hơn một pipeline đồng bộ nhiều collection. **Thêm read model** nên là quyết định có lý do từ workload, không phải phản xạ mặc định với mọi phép join.

## 15. Mô hình wide-column: tối ưu bằng cách đổi khóa truy cập

Trong Cassandra, bảng thường được thiết kế theo **partition key** và **clustering columns** để phục vụ một truy vấn biết trước. Nếu cần đọc sản phẩm theo productId:

~~~sql
-- Ví dụ CQL trên keyspace demo đã được cấu hình
CREATE TABLE catalog.products_by_id (
  tenant_id text,
  product_id text,
  title text,
  price_minor bigint,
  seller_id text,
  PRIMARY KEY ((tenant_id, product_id))
);
~~~

Một đường truy cập khác: “20 sản phẩm được công bố mới nhất của một danh mục trong tháng”. Có thể cần bảng:

~~~sql
CREATE TABLE catalog.products_by_category_month (
  tenant_id text,
  category_id text,
  month_bucket text,
  published_at timestamp,
  product_id text,
  title text,
  price_minor bigint,
  seller_name text,
  PRIMARY KEY (
    (tenant_id, category_id, month_bucket),
    published_at,
    product_id
  )
) WITH CLUSTERING ORDER BY (published_at DESC, product_id DESC);
~~~

Truy vấn một bucket:

~~~sql
SELECT product_id, title, price_minor, seller_name, published_at
FROM catalog.products_by_category_month
WHERE tenant_id = 'shop-a'
  AND category_id = 'stationery'
  AND month_bucket = '2026-11'
LIMIT 20;
~~~

Ở bảng thứ hai, **title**, **price_minor** và **seller_name** có thể là dữ liệu lặp từ nguồn sản phẩm/người bán. Đổi lại, đường đọc theo danh mục–tháng có thể truy cập một partition cụ thể và đọc các hàng được sắp sẵn.

Những điều cần lưu ý:

- Nếu truy vấn cần nhiều tháng, phải tính các **month_bucket** liên quan và gộp kết quả theo thứ tự.
- Nếu một danh mục có quá nhiều sản phẩm trong một tháng, partition có thể quá lớn/hot; có thể cần bucket nhỏ hơn hoặc shard.
- Nếu thay đổi **published_at** (một clustering key) hoặc di chuyển danh mục, có thể phải **xóa hàng khóa cũ rồi chèn hàng khóa mới**, không chỉ cập nhật một field như bình thường.
- Nếu đổi tên seller, mọi hàng dẫn xuất có seller_name liên quan cần đồng bộ/đối soát.
- Đọc từ hai bảng không mặc nhiên thấy một thay đổi cùng thời điểm; các bảng cần hợp đồng nhất quán riêng.

Đây là đặc trưng của thiết kế NoSQL theo truy vấn: **một thực thể có thể xuất hiện ở nhiều bảng được sắp theo những khóa khác nhau** để phục vụ các access patterns ưu tiên.

## 16. Key–value: cache một thẻ hay duy trì tập quan hệ?

Trong Redis, một cache thẻ sản phẩm có thể là một key:

~~~redis
SET product-card:shop-a:p-42 "{\"title\":\"Sổ tay A5\",\"priceMinor\":80000,\"sellerDisplayName\":\"Văn phòng phẩm An\"}" EX 60
GET product-card:shop-a:p-42
TTL product-card:shop-a:p-42
~~~

Khi hết hạn, ứng dụng dựng lại từ nguồn chính. Đây là **cache theo productId**, có thể giảm đọc lặp cho chi tiết/thẻ một sản phẩm. Nhưng **không tự phục vụ** truy vấn “20 sản phẩm mới nhất thuộc danh mục stationery”, vì cần một cách xác định và sắp thứ tự các productId thuộc danh mục.

Có thể dùng Sorted Set làm danh sách ID theo score thời gian, ví dụ:

~~~redis
ZADD category:shop-a:stationery:products 1794646800 "p-42"
ZREVRANGE category:shop-a:stationery:products 0 19
~~~

Score ở đây chỉ là **giá trị thời gian minh họa**. Khi lấy 20 ID, ứng dụng còn cần đọc product cards tương ứng, bảo đảm quyền truy cập và xử lý cache miss. Việc xóa một sản phẩm khỏi danh mục phải cập nhật tập chỉ mục, không chỉ xóa key thẻ.

Nếu dùng Redis Cluster, thao tác nhiều key có hạn chế theo hash slot và lệnh. Không được mặc định cập nhật product card cùng sorted set là một transaction nguyên tử trong mọi triển khai.

Giải pháp key–value thuận lợi cho những đường đọc đơn giản theo key, nhưng **giá trị có cấu trúc, tập ID và read model đều cần chính sách đồng bộ**. Cache miss, eviction, TTL và sự kiện đến sai thứ tự là một phần của thiết kế.

## 17. Quan hệ nhiều-nhiều: lặp hay ghép tùy hướng truy vấn

Xét học viên và khóa học:

~~~text
student-01 -> course-nosql
student-01 -> course-java
student-02 -> course-nosql
~~~

Nếu chỉ lưu **courseIds[]** trong student, màn hình “khóa của học viên” đơn giản nhưng màn hình “học viên của một khóa” có thể cần truy vấn ngược qua rất nhiều student.

Nếu lưu mảng ở **cả hai phía**:

~~~text
students.student-01.courseIds = [course-nosql, course-java]
courses.course-nosql.studentIds = [student-01, student-02]
~~~

ta có hai bản dữ liệu quan hệ cần cập nhật cùng nhau. Nếu một phía cập nhật thất bại, hai màn hình không đồng nhất.

Một mô hình nguồn chính riêng:

~~~javascript
{
  _id: "enrollment-101",
  tenantId: "school-a",
  studentId: "student-01",
  courseId: "course-nosql",
  status: "ACTIVE",
  enrolledAt: ISODate("2026-11-14T09:00:00Z")
}
~~~

Với **enrollments**, có thể tạo index theo student và index theo course, đồng thời dùng unique compound index theo bộ **(tenantId, studentId, courseId)** nếu nghiệp vụ chỉ cho một quan hệ của cặp. Cách này vừa có nguồn chính của mối quan hệ, vừa cung cấp hai đường đọc bằng index.

Chỉ khi các query vẫn không đáp ứng tải hoặc cần traversal nhiều hop, mới cân nhắc read model/adjacency list/graph edge theo yêu cầu cụ thể. **Không phải mọi quan hệ N:M đều cần lưu hai chiều thành hai bản sao dữ liệu nghiệp vụ.**

## 18. Cần đo cả chi phí đọc lẫn chi phí cập nhật

Một mô hình chỉ được xem là tối ưu khi kết quả được đo trên access patterns quan trọng.

### Các chỉ số nên thu thập

| Nhóm | Chỉ số | Câu hỏi trả lời |
|---|---|---|
| Đọc | p50/p95/p99 API latency | Người dùng thực sự chờ bao lâu? |
| Đọc | Database calls / request | Có N+1 hay quá nhiều round-trip không? |
| Đọc | Documents/keys examined | Có quét lớn hơn nhiều số bản ghi trả về không? |
| Đọc | Bytes returned/read | Document nhúng quá nhiều field không cần thiết? |
| Ghi | Số bản cập nhật / thay đổi nguồn | Write amplification có quá lớn không? |
| Ghi | p95 latency và conflict rate | Transaction/fan-out có làm chậm ghi nguồn? |
| Đồng bộ | Projection lag | Thời gian từ event nguồn đến khi read model đúng |
| Đồng bộ | Số event retry/dead-letter | Có bản sao bị bỏ sót hoặc kẹt không? |
| Đồng bộ | Version mismatch | Bản đọc nào đang thấp hơn nguồn? |
| Dung lượng | Bytes dữ liệu/index/backup | Lặp dữ liệu làm tăng tổng footprint bao nhiêu? |
| Đúng đắn | Checkout validation failures | UI dùng dữ liệu trễ có dẫn tới nhiều thao tác từ chối không? |
| Vận hành | Thời gian rebuild/backfill | Có thể phục hồi read model khi bị lỗi không? |

Một phép tính sơ bộ: **1.000.000 sản phẩm**, trung bình xuất hiện trong **2 danh mục**, và mỗi bản thẻ danh mục bổ sung **600 byte** dữ liệu hữu ích:

\[
1\,000\,000 \times 2 \times 600
= 1\,200\,000\,000\ \text{bytes}
\approx 1{,}2\ \text{GB (thập phân)}
\]

Con số 1,2 GB chỉ mô tả **payload dữ liệu thô ở bản đọc**. Thực tế còn index, metadata, nén, replication, không gian trống, log và backup. Nếu mỗi bản ghi nguồn chỉ được cập nhật một lần nhưng read model phải ghi nhiều bản, chi phí I/O và vận hành có thể quan trọng hơn dung lượng raw.

Trong Cassandra hoặc các hệ phân tán, còn cần xét partition size, hot partition và việc nhân bản dữ liệu vào nhiều table có cùng key khác nhau. Trong MongoDB, cần đo **totalDocsExamined**, **totalKeysExamined**, plan của $lookup và hiệu quả index. Trong Redis, đo RAM, eviction, hit ratio và latency của các lệnh nhiều key.

## 19. Khi nào mô hình hạn chế lặp có thể là lựa chọn tốt hơn?

Những tình huống thường nghiêng về tham chiếu và ít bản sao:

- Thông tin được **nhiều thực thể dùng chung** và **thay đổi thường xuyên**, ví dụ tồn kho hoặc quyền hiện tại.
- Dữ liệu có yêu cầu **độ mới chặt chẽ** nhưng hệ không có cơ chế đồng bộ đủ mạnh cho các bản sao.
- Số bản sao tiềm năng rất lớn, một thay đổi có thể phải fan-out đến hàng triệu document.
- Đường đọc truy cập theo ID, số thực thể tham chiếu ít và **batch lookup/$lookup đã đủ nhanh**.
- Dữ liệu nhạy cảm hoặc có yêu cầu xóa/thu hồi quyền khiến việc nhân bản tăng rủi ro.
- Chi phí vận hành read model không đáng so với lợi ích đọc.

Ví dụ tên seller có thể được lấy qua cache tập trung theo **sellerId**, thay vì nhân bản vào từng product card nếu seller sở hữu rất nhiều sản phẩm và đổi tên tương đối thường xuyên.

**Hạn chế lặp không đồng nghĩa không có index.** Một collection vẫn cần các index phục vụ lookup và sort. Chọn chuẩn hóa ở mức nghiệp vụ không có nghĩa từ chối mọi tối ưu lưu trữ bên dưới.

## 20. Khi nào mô hình tối ưu đường truy cập có thể đáng giá?

Những tình huống thường nghiêng về read model/phi chuẩn hóa:

- Một màn hình có **lưu lượng đọc rất cao**, nhiều dữ liệu phải ghép và chi phí đọc đã được đo là điểm nghẽn.
- Đường lọc/sort khó phục vụ từ schema nguồn mà không quét lượng dữ liệu lớn.
- Dữ liệu dẫn xuất cần tương đối ít trường, **không đổi quá thường xuyên**, và chấp nhận độ trễ đồng bộ hữu hạn.
- Có thể xây dựng **source of truth, pipeline retry, idempotency, versioning, đối soát**.
- Việc tách read model giúp giữ đơn vị ghi nguồn nhỏ và rõ bất biến.
- Hệ cột rộng/key–value yêu cầu sắp dữ liệu theo khóa của truy vấn cụ thể.

Ví dụ một dashboard cần “top 20 sản phẩm bán chạy tuần này” có thể được phục vụ bởi aggregate theo tuần thay vì mỗi request quét toàn bộ order đã thanh toán.

Nhưng nếu kết quả top 20 dùng để phân chia thưởng/doanh thu hoặc quyết định có giá trị tài chính, cần chốt cách tính, độ trễ, dữ liệu đến muộn, chống đếm trùng và đối soát với nguồn đơn hàng.

## 21. Chiến lược chuyển đổi an toàn từ mô hình nguồn sang read model

Một team có thể bắt đầu với mô hình tham chiếu, sau đó thêm read model khi số liệu tải chứng minh cần thiết. Không cần “big bang migration” rồi lập tức chuyển toàn bộ người dùng.

~~~mermaid
flowchart TD
    A["Mô hình nguồn đang phục vụ"] --> B["Định nghĩa hợp đồng product_cards"]
    B --> C["Backfill read model từ nguồn"]
    C --> D["Ghi nhận thay đổi mới (CDC/outbox)"]
    D --> E["Đối soát version, count và fields"]
    E --> F["Shadow read / so kết quả"]
    F --> G{"Đúng và đủ nhanh?"}
    G -->|Chưa| H["Sửa pipeline, rebuild, quan sát"]
    H --> E
    G -->|Có| I["Chuyển dần lưu lượng đọc"]
    I --> J["Theo dõi lag, lỗi và phương án rollback"]
~~~

### Bước 1 — Chốt hợp đồng dữ liệu

Đặt tên rõ **product_cards**, trường nào là bản copy của nguồn nào, field nào có thể trễ, key nào dùng truy vấn, cách xử lý không có seller/inventory và điều kiện phân quyền.

### Bước 2 — Backfill dữ liệu lịch sử

Dựng read model từ các collection gốc theo batch có checkpoint. Cần xử lý sự kiện nguồn thay đổi trong lúc backfill để tránh tình trạng snapshot cũ ghi đè event mới. Có thể dùng snapshot đồng bộ với luồng CDC hoặc version/sequence để hòa giải; cách cụ thể tùy database.

### Bước 3 — Bắt thay đổi mới

Thiết kế outbox/change stream, consumer idempotent và quy tắc version. Khi producer có nhiều thao tác ghi, phải biết một event đại diện cho thay đổi nào và khi nào được coi là đã commit.

### Bước 4 — Đối chiếu kết quả

So count theo tenant/category, danh sách ID theo truy vấn, các trường quan trọng, version và tỷ lệ mismatch. Chỉ kiểm tra số document bằng nhau **không đủ** vì có thể cùng số lượng nhưng sai giá/trạng thái.

### Bước 5 — Chạy song song

Shadow read một phần request từ cả nguồn và read model, so khác biệt theo mức trễ được phép. Không đưa bản shadow vào kết quả khách hàng nếu chưa được phê duyệt về bảo mật hoặc độ đúng.

### Bước 6 — Chuyển dần và có đường lùi

Feature flag/canary giúp chuyển một tỷ lệ lưu lượng, theo dõi p95/p99, lag và lỗi. Giữ khả năng đọc nguồn cũ trong giai đoạn đầu, đồng thời biết cách xử lý khi read model bị chậm hoặc mất checkpoint.

**Rebuildability** là lợi thế lớn khi read model chỉ chứa dữ liệu dẫn xuất: có thể xóa và dựng lại nếu nguồn và lịch sử thay đổi đủ để tái tạo. Nhưng khả năng dựng lại phải được kiểm chứng, không được coi là hiển nhiên nếu log thay đổi bị giữ quá ngắn.

## 22. Dữ liệu bị xóa, thay đổi quyền và bản sao ngoài ý muốn

Phi chuẩn hóa tăng số nơi dữ liệu có thể tồn tại:

~~~text
Nguồn:
  products / sellers / inventory

Bản dẫn xuất:
  product_cards
  Redis cache
  search index
  analytics export
  backup/snapshot
~~~

Khi seller yêu cầu xóa thông tin cá nhân hoặc một sản phẩm bị thu hồi, chỉ xóa record nguồn không có nghĩa mọi bản sao biến mất ngay. Cần xác định:

- Bản nào phải xóa, bản nào giữ theo căn cứ hợp lệ và thời hạn bao lâu?
- Event **delete/unpublish** có được ưu tiên để chặn phục vụ dữ liệu đã thu hồi không?
- Cache có TTL, invalidation hoặc truy vấn nguồn tại thời điểm nhạy cảm không?
- Consumer có thể chạy lại event **upsert cũ** sau event delete và làm dữ liệu xuất hiện lại không?
- Search index/read model có checkpoint và cơ chế phát hiện bản mồ côi không?
- Backup/restore có quy trình áp dụng lại yêu cầu xóa trước khi mở cho người dùng không?

Một **tombstone/deletion marker có version** hoặc deletion ledger tối thiểu có thể giúp chặn tái tạo bản đã xóa khi replay; phải thiết kế theo phạm vi quyền và chính sách lưu giữ. Không được coi việc xóa một cache key bằng TTL là đáp ứng trọn vẹn yêu cầu xóa theo chủ thể.

**Độ trễ đồng bộ được phép cho tên người bán không đương nhiên là độ trễ được phép cho thay đổi quyền truy cập hoặc yêu cầu thu hồi thông tin.** Phân loại sự kiện theo mức nghiêm trọng và hợp đồng nghiệp vụ.

## 23. Bảng quyết định cho một hệ thống mới

| Câu hỏi thiết kế | Nếu câu trả lời là “có” | Hướng cân nhắc |
|---|---|---|
| Dữ liệu con nhỏ, giới hạn và được đọc cùng cha? | Có | Nhúng vào document/item |
| Đối tượng có danh tính, được dùng chung và cập nhật độc lập? | Có | Tham chiếu nguồn chính |
| Có hàng nghìn/hàng triệu quan hệ N:M? | Có | Association/edge riêng, index hai chiều |
| Một read path rất nhiều lượt ghép và là bottleneck đã đo? | Có | Batch lookup, join tối ưu, cache rồi mới cân nhắc read model |
| Cần sort/filter theo chiều khác primary key của wide-column store? | Có | Bảng truy cập/read model theo khóa khác |
| Một field phải hiện đúng tức thì ở mọi quyết định quan trọng? | Có | Không dựa duy nhất vào bản sao eventual |
| Giá trị là snapshot tại thời điểm giao dịch? | Có | Nhúng snapshot, không đồng bộ ngược theo catalog |
| Một thay đổi nguồn ảnh hưởng rất nhiều bản sao? | Có | Định lượng write amplification và fan-out |
| Có pipeline retry/version/rebuild/đối soát đáng tin? | Không | Hạn chế số bản dẫn xuất quan trọng |
| Dữ liệu có yêu cầu xóa hoặc phân quyền nghiêm ngặt? | Có | Giảm lặp không cần thiết, có quy trình propagation rõ |

Một quyết định có thể được ghi bằng **ADR (Architecture Decision Record)** ngắn:

~~~markdown
## Quyết định: product_cards cho trang danh mục

Access pattern:
- 20 sản phẩm theo tenant/category, mới cập nhật gần nhất

Nguồn chính:
- products: title/price/published/category
- sellers: displayName
- inventory: availableStock

Read model:
- product_cards gồm fields cần hiển thị; availability chỉ là hint

Độ mới cho phép:
- sellerDisplayName <= 30 giây (ví dụ)
- checkout bắt buộc xác minh price + stock tại nguồn

Đồng bộ:
- outbox/change stream + consumer idempotent + source versions
- job đối soát, rebuild từ nguồn

Rủi ro:
- fan-out khi seller đổi tên
- bản sao stale, event sai thứ tự, xóa dữ liệu

Kiểm chứng:
- API p95/p99, documents examined, lag/mismatch rate,
  write amplification, thời gian rebuild
~~~

ADR giúp những người bảo trì sau này hiểu vì sao có trường lặp, trường nào **không được coi là nguồn sự thật** và khi nào nên xem xét lại quyết định.

## 24. Những nhầm lẫn phổ biến

| Nhầm lẫn | Vấn đề | Cách hiểu đúng |
|---|---|---|
| “NoSQL bắt buộc phi chuẩn hóa hết” | Tăng bản sao vô ích và khó cập nhật | Chọn theo access pattern, chủ sở hữu và bất biến |
| “Tránh lặp nghĩa là không cần tối ưu index” | Truy vấn vẫn có thể quét lớn | Tham chiếu và index là hai quyết định khác nhau |
| “Một $lookup luôn chậm” | Có thể chỉ ghép 20 document và được hỗ trợ bởi index | Đo thực tế trước khi thay mô hình |
| “Một read model luôn nhanh hơn nguồn” | Query có thể thiếu index, partition quá lớn hoặc dữ liệu trễ | Vẫn phải thiết kế khóa/index, đo latency và tính đúng |
| “Bản sao là nguồn sự thật thứ hai” | Hai nguồn cạnh tranh khi cập nhật | Chỉ rõ canonical source và dữ liệu dẫn xuất |
| “Event đã publish là mọi bản sao đã đúng” | Consumer có thể chậm/lỗi/mất event | Retry, checkpoint, version, đối soát |
| “Đặt TTL là đủ giữ dữ liệu mới” | TTL không bảo đảm độ mới đúng ngưỡng mọi trường | Invalidation/version và kiểm tra nguồn khi cần |
| “Cứ update lại toàn bộ sản phẩm khi seller đổi tên” | Fan-out lớn, dễ lỗi một phần | Cân nhắc join/cache tập trung, batch và write amplification |
| “Nhân bản giá/tồn để checkout không cần đọc nguồn” | Có thể bán quá tồn hoặc lấy giá cũ | Thẻ hiển thị và nghiệp vụ xác nhận có yêu cầu khác nhau |
| “Snapshot đơn hàng là bản cache sai thời hạn” | Có thể ghi đè lịch sử đã chốt | Snapshot phải giữ trạng thái tại thời điểm giao dịch |
| “Giảm số truy vấn nghĩa là giảm toàn bộ chi phí” | Tốn thêm ghi, index, lưu trữ, đồng bộ và xóa | Đánh giá tổng chi phí đọc–ghi–vận hành |
| “Tạo một read model cho mọi màn hình” | Hình dạng quá lớn và không tối ưu đường nào | Mô hình theo nhóm truy vấn cụ thể |

## 25. Quy trình thực hành ra quyết định

~~~mermaid
flowchart TD
    A["Liệt kê read/write access patterns"] --> B["Xác định source of truth và bất biến"]
    B --> C["Thiết kế nguồn hạn chế lặp hợp lý"]
    C --> D["Đo query, index, join và latency"]
    D --> E{"Đáp ứng SLO và chi phí?"}
    E -->|"Có"| F["Giữ mô hình đơn giản, theo dõi"]
    E -->|"Không"| G["Batch lookup, projection, index, cache"]
    G --> H{"Đã đáp ứng?"}
    H -->|"Có"| F
    H -->|"Không"| I["Thiết kế read model theo đường truy cập"]
    I --> J["Định nghĩa consistency, version, retry, deletion"]
    J --> K["Backfill + shadow read + đối soát"]
    K --> L{"Đúng và đủ nhanh?"}
    L -->|"Không"| J
    L -->|"Có"| M["Chuyển dần lưu lượng, giám sát"]
~~~

Từng bước:

1. **Viết yêu cầu:** Input/filter/sort/limit/fields, tần suất đọc và mức độ mới.
2. **Chỉ rõ chủ sở hữu:** ai ghi tên, giá, stock, quyền; đâu là snapshot lịch sử.
3. **Xác định bất biến:** những field nào không được sai khi xác nhận nghiệp vụ.
4. **Bắt đầu với mô hình đủ đơn giản:** reference/embedding có giới hạn, index và key hợp lý.
5. **Đo nút thắt:** số thao tác, bytes, plan, p95/p99, contention.
6. **Tối ưu đường đọc hiện tại:** projection, pagination, batch reads, lookup/index trước khi nhân bản vô hạn.
7. **Chọn read model khi thực sự cần:** đúng trường, đúng khóa, đúng độ mới.
8. **Thiết kế đường đồng bộ:** atomic/outbox, event ID/version, retry, rebuild và đối soát.
9. **Đặt kiểm thử dữ liệu trễ và lỗi một phần:** cập nhật đồng thời, sự kiện sai thứ tự, xóa và restore.
10. **Theo dõi sau triển khai:** read latency, write amplification, projection lag, mismatch, chi phí.

Điểm cần nhớ là **đường đọc quyết định hình dạng dữ liệu cần có**, nhưng **bất biến và quyền sở hữu quyết định dữ liệu nào được phép là nguồn chính**. Tối ưu đọc chỉ bền vững khi có cơ chế giữ bản dẫn xuất phù hợp với những quy tắc đó.

## 26. Bài tập áp dụng

### Bài tập 1 — So sánh hai cách lưu

Một hệ có **products**, **sellers** và **inventory**. Trang danh mục hiển thị 20 sản phẩm, tên người bán và trạng thái tồn. Hãy vẽ hai cách thiết kế: nguồn riêng + reference, và **product_cards**. Với mỗi cách, liệt kê số đường truy vấn, nơi cập nhật nguồn và điểm có thể phát sinh dữ liệu trễ.

### Bài tập 2 — Định lượng fan-out

Một seller có **80.000 sản phẩm**, đổi displayName ba lần mỗi tháng. Có **10.000 request trang danh mục mỗi phút**, mỗi trang 20 sản phẩm. Hãy ước lượng khối lượng cập nhật bản sao khi dùng product cards, và đối chiếu với khối lượng truy vấn/ghép ở mô hình tham chiếu. Nêu lý do những phép đếm lý thuyết chưa đủ để quyết định nếu thiếu cache, index, batch, nén và phân bố tải.

### Bài tập 3 — Chọn trường nên phi chuẩn hóa

Xét **title**, **sellerName**, **priceMinor**, **stockExact**, **stockBadge**, **passwordHash** và **ratingAvg**. Hãy phân loại field có thể đưa vào read model công khai, field phải xác minh tại nguồn và field không nên xuất hiện. Với từng lựa chọn, nêu yêu cầu độ mới hoặc bảo mật.

### Bài tập 4 — Sự kiện sai thứ tự

Seller đổi tên qua version **9 → 10 → 11** nhưng consumer nhận event theo thứ tự **11, 9, 10**. Nếu mỗi event ghi đè thẳng sellerName trong product_cards thì kết quả cuối có thể là gì? Đề xuất điều kiện cập nhật dựa trên **sellerVersion** để không quay ngược về dữ liệu cũ.

### Bài tập 5 — Cập nhật nguồn thành công nhưng publish thất bại

Sau khi cập nhật seller, ứng dụng chết trước khi gửi event. Hãy mô tả cách dùng **outbox** hoặc **change stream** để khôi phục, vì sao consumer cần idempotency và bằng chứng nào cho thấy read model đã hội tụ.

### Bài tập 6 — Đường truy vấn thay đổi

Ban đầu ứng dụng chỉ đọc product theo ID. Sau đó có trang top 20 sản phẩm theo danh mục và trang top seller của tuần. Hãy đề xuất index, join/batch read, cache hoặc read model khác nhau cho từng đường truy cập. Chỉ rõ trường nào là nguồn chính và dữ liệu tổng hợp nào có thể trễ.

### Bài tập 7 — Dữ liệu lịch sử

Giá một sản phẩm tăng từ 80.000 lên 90.000 VND sau khi khách thanh toán. Nếu order item lưu **unitPriceAtPurchase = 80.000**, có cần đồng bộ thành 90.000 không? Hãy phân biệt snapshot hóa đơn với cache giá sản phẩm và read model trang danh sách.

### Bài tập 8 — Từ mô hình quan hệ N:M sang read model

Học viên tham gia nhiều khóa; một khóa có nhiều học viên. Hãy thiết kế **enrollments** làm nguồn quan hệ với unique key, index theo cả hai chiều. Trong điều kiện nào bạn mới cần hai bản danh sách kề hoặc graph edge, và làm sao tránh hai nguồn quan hệ không nhất quán?

### Bài tập 9 — Wide-column và nhân bản

Một hệ Cassandra cần đọc sản phẩm theo productId và đọc top sản phẩm mới của category trong mỗi tháng. Hãy đề xuất hai bảng theo khóa tương ứng. Khi title/price đổi, dữ liệu nào phải cập nhật ở các bảng, và điều gì xảy ra khi một cập nhật thành công nhưng cập nhật kia thất bại?

### Bài tập 10 — Di chuyển an toàn

Hệ đang dùng $lookup trên sources, muốn tạo product_cards. Hãy thiết kế quy trình backfill, bắt event mới, so sánh kết quả, shadow read, chuyển traffic, rollback và rebuild. Nêu tối thiểu năm metrics cần theo dõi trong giai đoạn chuyển đổi.

### Bài tập 11 — Xóa và thu hồi quyền

Một seller bị khóa tài khoản và yêu cầu gỡ hồ sơ khỏi giao diện. Tên seller còn ở product cards, Redis cache, search index và bản xuất phân tích. Hãy phân biệt nhu cầu **chặn hiển thị ngay** với việc **xóa dữ liệu theo chính sách**, rồi mô tả cách tránh consumer phát lại sự kiện cũ làm hồ sơ xuất hiện trở lại.

### Bài tập 12 — Đưa ra quyết định dựa trên số liệu

Một nhóm đề xuất sao chép toàn bộ thông tin seller vào 500.000 product records để “khỏi join”. Hãy lập bảng gồm **lượt đọc/s, tần suất đổi seller, fan-out mỗi lần đổi, byte thừa, latency hiện tại, lag cho phép và thời gian rebuild**. Đưa ra điều kiện nào ủng hộ dùng read model, điều kiện nào ủng hộ batch lookup/reference.

---

**Kết luận:** Mô hình hạn chế lặp dữ liệu ưu tiên **một nguồn sở hữu rõ ràng, cập nhật tập trung và giảm sai lệch giữa các bản sao**. Mô hình tối ưu đường truy cập ưu tiên **đưa đúng hình dạng dữ liệu đến gần truy vấn**, có thể cần thêm bản dẫn xuất, index và pipeline đồng bộ. Một kiến trúc NoSQL hiệu quả thường kết hợp cả hai: **nguồn chính giữ bất biến nghiệp vụ, bản đọc được tổ chức theo access pattern, và mọi dữ liệu lặp có hợp đồng cập nhật–độ mới–xóa–đối soát**. Quyết định phải được đo qua cả hiệu năng đọc, chi phí ghi và độ tin cậy vận hành, không chỉ qua số lượng collection hay số lần join.
