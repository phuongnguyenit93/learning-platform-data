# Chọn mức độ chi tiết phù hợp với từng ngữ cảnh

Khi xây dựng mô hình domain, đội phát triển thường đứng trước hai câu hỏi: cần mô tả một khái niệm đến mức nào, và những thông tin nào nên xuất hiện trong mô hình đó? Một sản phẩm trong hệ thống thương mại điện tử có thể cần tên, hình ảnh, mô tả, giá bán, mã SKU, số lượng tồn, vị trí trong kho, kích thước đóng gói và nhiều thuộc tính khác. Nhưng không phải Bounded Context nào cũng cần tất cả những thông tin này.

Product Catalog cần mô tả sản phẩm để khách tìm kiếm và lựa chọn. Sales cần ghi nhận khách đã mua mặt hàng nào, với số lượng và mức giá nào tại thời điểm đặt hàng. Inventory cần quản lý mã hàng và số lượng có thể bán trong từng kho. Fulfillment cần biết mặt hàng nào phải được lấy, đóng gói và bàn giao. Nếu ép các context dùng chung một mô hình Product thật lớn, mô hình sẽ chứa nhiều dữ liệu và quy tắc không liên quan đến trách nhiệm của từng nơi. Nếu mô hình quá sơ sài, nó lại không thể bảo vệ những quyết định nghiệp vụ quan trọng.

Trong Domain-Driven Design (DDD), mức độ chi tiết của mô hình cần phù hợp với **ngữ cảnh, mục tiêu sử dụng và các quyết định nghiệp vụ mà ngữ cảnh chịu trách nhiệm**. Một mô hình tốt không phải mô hình có nhiều thuộc tính nhất. Đó là mô hình diễn đạt đủ chính xác những khái niệm, hành vi và bất biến cần thiết trong phạm vi của nó.

Sau bài học này, bạn có thể:

- Giải thích vì sao mỗi Bounded Context có thể cần mức độ chi tiết khác nhau cho cùng một khái niệm.
- Chọn thông tin và quy tắc cần có dựa trên use case, quyết định và invariant.
- Nhận diện mô hình quá chi tiết hoặc quá sơ sài.
- Phân biệt domain model với read model và dữ liệu snapshot.
- Thiết kế cách trao đổi dữ liệu giữa các context mà không làm rò mô hình nội bộ.

## 1. Mức độ chi tiết của mô hình có nghĩa là gì?

Mức độ chi tiết (*level of detail* hoặc *granularity*) thể hiện mô hình mô tả một khái niệm sâu đến đâu, phân biệt những trường hợp nào và bảo vệ những quy tắc nào. Nó không chỉ là số lượng field trong một class.

Ví dụ, một mô hình `Customer` có thể chỉ cần `CustomerId` và tên hiển thị trong một màn hình tra cứu. Nhưng trong một ngữ cảnh quản lý tín dụng, Customer có thể cần hồ sơ định danh, lịch sử đánh giá, quan hệ bảo lãnh, hạn mức, trạng thái tuân thủ và các mốc hiệu lực. Hai mô hình có mức độ chi tiết khác nhau vì chúng phục vụ những quyết định khác nhau.

Có thể nhìn mức độ chi tiết qua ba câu hỏi:

1. **Mô hình cần biết những gì?** Các thuộc tính, khái niệm liên quan và dữ liệu lịch sử nào cần thiết?
2. **Mô hình cần phân biệt điều gì?** Những trạng thái, loại đối tượng hoặc trường hợp nào có ý nghĩa riêng?
3. **Mô hình cần bảo vệ quy tắc nào?** Những điều kiện nào phải luôn đúng khi thực hiện hành vi nghiệp vụ?

Ví dụ, nếu hệ thống chỉ hiển thị tên sản phẩm, một cấu trúc dữ liệu gồm mã và tên có thể đủ cho màn hình đó. Nhưng nếu hệ thống quyết định có được đặt mua hay không, nó cần biết giá đã chốt, điều kiện bán, số lượng, trạng thái đơn và các quy tắc liên quan. Nếu quyết định giữ hàng, nó cần mô hình tồn kho và reservation có khả năng bảo vệ invariant về số lượng.

Vì vậy, không thể kết luận một mô hình tốt chỉ bằng cách đếm field, class hoặc bảng. Cần xem mô hình có hỗ trợ đúng quyết định trong ngữ cảnh hay không.

## 2. Bounded Context quyết định phạm vi của mô hình

Một Bounded Context là phạm vi mà một mô hình domain và ngôn ngữ chung có ý nghĩa nhất quán. Mỗi context chịu trách nhiệm cho một phần nghiệp vụ và có thể cần một cách biểu diễn riêng cho những khái niệm xuất hiện ở nhiều nơi.

Hãy xét khái niệm `Product` trong bốn context:

| Context | Câu hỏi nghiệp vụ chính | Chi tiết Product cần quan tâm |
|---|---|---|
| Product Catalog | Khách có thể tìm hiểu và lựa chọn mặt hàng nào? | Tên, mô tả, hình ảnh, danh mục, thuộc tính công bố, biến thể và trạng thái xuất bản |
| Sales | Khách đã đồng ý mua mặt hàng nào và với điều kiện nào? | Mã tham chiếu sản phẩm, SKU, tên và giá đã chốt, số lượng, chiết khấu hoặc thông tin thuế cần lưu theo giao dịch |
| Inventory | Có bao nhiêu đơn vị hàng có thể bán hoặc giữ? | SKU, kho, số lượng vật lý, số lượng đã giữ, số lượng khả dụng và quy tắc reservation |
| Fulfillment | Nhân viên cần lấy và đóng gói mặt hàng nào? | SKU hoặc mã vạch, số lượng cần lấy, kích thước, trọng lượng, yêu cầu bảo quản và hướng dẫn xử lý |

Các context có thể cùng tham chiếu đến một mặt hàng ngoài đời thực, nhưng chúng không cần cùng một class `Product`. Product Catalog quan tâm đến nội dung công bố; Sales cần bằng chứng về điều kiện mua đã chốt; Inventory cần quản lý lượng hàng; Fulfillment cần nhận diện và thao tác với hàng vật lý.

Một mô hình Catalog có thể chứa hàng chục thuộc tính mô tả mà Inventory không cần biết. Ngược lại, Inventory cần chi tiết về reservation và vị trí kho mà Catalog không nên sở hữu. Nếu gộp tất cả vào một model, các thay đổi ở một context dễ tác động không cần thiết đến context khác.

### Cùng một từ không có nghĩa phải cùng một cấu trúc

Ngôn ngữ chung (*Ubiquitous Language*) cần nhất quán bên trong từng Bounded Context. Điều đó không có nghĩa toàn doanh nghiệp phải dùng một mô hình duy nhất cho mọi từ.

Trong Catalog, `Product` có thể là sản phẩm được công bố. Trong Sales, `OrderLine` có thể giữ một snapshot của thông tin sản phẩm tại thời điểm mua. Trong Inventory, `StockItem` đại diện cho đơn vị được theo dõi tồn kho. Những tên gọi và cấu trúc này khác nhau vì chúng thể hiện những khía cạnh khác nhau của domain.

Khi trao đổi qua ranh giới, context gửi và context nhận cần có hợp đồng cùng cách chuyển đổi rõ ràng. Context nhận chỉ nên lấy dữ liệu cần cho quyết định của mình, không phụ thuộc toàn bộ mô hình nội bộ của context gửi.

## 3. Chọn chi tiết dựa trên mục tiêu và use case

Trước khi thêm một thuộc tính hoặc khái niệm vào mô hình, hãy xác định use case nào cần nó. Một mô hình thường tồn tại để hỗ trợ các hành vi và quyết định cụ thể, chẳng hạn:

- Tìm kiếm và hiển thị sản phẩm.
- Chấp nhận hoặc từ chối một đơn hàng.
- Tính số tiền cần thanh toán.
- Giữ số lượng tồn kho.
- Xác định hàng cần lấy và cách đóng gói.
- Giải thích một quyết định đã xảy ra trong quá khứ.

Với mỗi use case, hãy hỏi:

- Actor muốn đạt được kết quả gì?
- Mô hình phải đưa ra quyết định nào?
- Dữ liệu nào là đầu vào của quyết định?
- Quy tắc nào phải luôn được bảo vệ?
- Những ngoại lệ nào làm thay đổi kết quả?
- Có cần lưu lại giá trị tại thời điểm xảy ra giao dịch không?

Ví dụ, use case “đặt hai chiếc túi” trong Sales không cần toàn bộ mô tả marketing hoặc ảnh sản phẩm. Nó cần biết khách đang mua SKU nào, số lượng bao nhiêu, mức giá và điều kiện thương mại nào đã được chấp nhận. Nếu giá có thể thay đổi sau đó, Order Line cần lưu giá đã chốt để lịch sử giao dịch không bị thay đổi theo Catalog.

Ngược lại, use case “khách tìm túi màu đen” trong Catalog cần thuộc tính màu sắc, mô tả và thông tin tìm kiếm. Nó không cần số lượng đã reserve trong từng kho để xác định nội dung sản phẩm. Nếu cần hiển thị khả năng có hàng, Catalog có thể sử dụng thông tin khả dụng được cung cấp từ Inventory qua một hợp đồng phù hợp.

## 4. Dùng quyết định nghiệp vụ và invariant để xác định độ sâu

Một mô hình domain cần đủ chi tiết để đưa ra quyết định đúng và bảo vệ invariant của nó. Invariant là điều kiện phải luôn đúng trong phạm vi consistency boundary của mô hình, thường được bảo vệ bởi Aggregate.

Ví dụ trong Sales:

- Order phải có ít nhất một dòng hàng khi được đặt.
- Số lượng của một Order Line phải lớn hơn 0.
- Giá đã chốt không được thay đổi âm thầm sau khi Order được xác nhận.
- Order chỉ được chuyển sang trạng thái nhất định khi đáp ứng điều kiện của chính sách bán hàng.

Ví dụ trong Inventory:

- Không thể reserve nhiều hơn số lượng khả dụng theo quy tắc tồn kho.
- Một reservation phải tham chiếu đến SKU và kho hợp lệ.
- Không được giải phóng cùng một reservation nhiều lần theo cách làm tăng tồn khả dụng sai lệch.

Những invariant này đòi hỏi mức chi tiết khác nhau. Sales cần `Order`, `OrderLine`, `Money`, `Quantity` và các chính sách liên quan. Inventory cần `StockItem`, `Warehouse`, `Reservation` và các phép tính tồn kho. Việc đưa tất cả các khái niệm này vào một Aggregate Product sẽ tạo ra một consistency boundary quá rộng và gắn những quyết định không cùng trách nhiệm.

### Mô hình càng chi tiết khi quyết định càng cần phân biệt

Hãy xem xét một quyết định hoàn tiền. Nếu chính sách chỉ cần biết giao dịch đã thu bao nhiêu và số tiền được phép hoàn, mô hình có thể cần `Money`, `PaymentReference` và `RefundPolicy`. Nếu chính sách phân biệt phí vận chuyển, thuế, giảm giá, hàng khuyến mại và hoàn một phần, mô hình phải diễn đạt các thành phần đó riêng biệt.

Không nên thêm chi tiết chỉ vì dữ liệu có sẵn. Hãy thêm khi nó làm thay đổi một quyết định, bảo vệ một quy tắc, giải thích lịch sử hoặc hỗ trợ một use case đã xác định.

## 5. Ba mức nhìn để xây dựng mô hình

Trong quá trình thiết kế, có thể đi từ mô tả khái niệm đến mô hình có quy tắc và cuối cùng là cấu trúc triển khai. Đây là các mức nhìn bổ trợ, không phải ba loại Bounded Context.

### Mức khái niệm: xác định điều gì tồn tại trong domain

Ở mức này, nhóm thống nhất các thuật ngữ và quan hệ quan trọng. Ví dụ trong Sales: Order, Order Line, Customer, Payment Reference, Cancellation. Chưa cần quyết định mỗi khái niệm là class, bảng hay service.

Mục tiêu là làm rõ ý nghĩa: Order được hình thành khi nào? Order Line khác Product thế nào? Ai có thể hủy Order? Một Order có thể được thực hiện qua nhiều Shipment không?

### Mức quy tắc: xác định hành vi và giới hạn

Ở mức này, mô hình diễn đạt trạng thái, hành vi, điều kiện và invariant. Ví dụ, Order chỉ có thể được đặt khi có ít nhất một dòng hàng; sau khi xác nhận, giá của các dòng hàng được giữ theo điều kiện đã chấp thuận.

Nhóm có thể xác định Entity, Value Object, Aggregate, Domain Service và Domain Event nếu chúng giúp biểu đạt domain rõ hơn.

### Mức triển khai: chọn cấu trúc kỹ thuật phù hợp

Ở mức này, đội phát triển quyết định class, module, repository, database mapping, API contract và cách lưu trữ. Cấu trúc code nên hỗ trợ mô hình và ranh giới đã hiểu, không thay thế việc khám phá domain.

Ví dụ, `Money` có thể là Value Object trong domain model, được lưu thành hai cột `amount` và `currency`. Cấu trúc lưu trữ đó không làm thay đổi ý nghĩa nghiệp vụ của Money. Tương tự, một Aggregate có thể được lưu qua nhiều bảng nhưng vẫn là một consistency boundary của domain.

## 6. Tránh mô hình quá chi tiết

Mô hình quá chi tiết (*over-modeling*) đưa vào nhiều khái niệm, thuộc tính hoặc abstraction không giúp ích cho quyết định nghiệp vụ hiện tại. Nó làm tăng số lượng quy tắc phải duy trì và khiến thành viên khó nhận ra phần nào thực sự quan trọng.

Một số dấu hiệu:

- Mỗi field của một hệ thống bên ngoài đều được đưa vào domain model dù không có use case sử dụng.
- Một class chứa nhiều thuộc tính chỉ phục vụ màn hình hoặc báo cáo riêng lẻ.
- Mô hình có nhiều trạng thái nhưng chuyên gia nghiệp vụ không phân biệt được ý nghĩa của chúng.
- Một thao tác CRUD đơn giản bị bao quanh bởi nhiều lớp và abstraction không bảo vệ quy tắc nào.
- Một context phải hiểu các chi tiết của context khác dù không đưa ra quyết định liên quan.
- Mỗi thay đổi nhỏ đều đòi hỏi cập nhật nhiều object chỉ vì chúng dùng chung một model quá lớn.

Ví dụ, Inventory cần biết SKU, kho và số lượng có thể reserve. Nếu nó phải nạp toàn bộ Product gồm mô tả marketing, hình ảnh, SEO metadata, video và nội dung chiến dịch chỉ để giữ hàng, mô hình đang mang quá nhiều chi tiết không thuộc trách nhiệm của Inventory.

### Cách giảm độ chi tiết không cần thiết

1. Liệt kê use case thực sự dùng mô hình.
2. Đánh dấu field nào tham gia quyết định hoặc invariant.
3. Chuyển dữ liệu chỉ dùng để hiển thị sang read model nếu phù hợp.
4. Giữ dữ liệu của context khác ở dạng reference hoặc contract tối thiểu.
5. Xóa abstraction không có trách nhiệm domain rõ ràng sau khi xác nhận không còn consumer.

Không nên hiểu “đơn giản” là loại bỏ mọi chi tiết. Một quy tắc phức tạp nhưng quan trọng vẫn cần được mô hình hóa đầy đủ. Mục tiêu là bỏ phần không phục vụ trách nhiệm, không phải bỏ phần làm nên ý nghĩa domain.

## 7. Tránh mô hình quá sơ sài

Mô hình quá sơ sài (*under-modeling*) không thể diễn đạt các quyết định và invariant quan trọng. Khi đó, logic nghiệp vụ thường bị đẩy vào controller, câu truy vấn, script hoặc các điều kiện rời rạc.

Một số dấu hiệu:

- Một Entity chỉ có getter/setter trong khi nghiệp vụ có nhiều hành vi và điều kiện chuyển trạng thái.
- Các giá trị quan trọng như tiền, số lượng, tỷ lệ hoặc khoảng thời gian chỉ được lưu bằng kiểu dữ liệu nguyên thủy và không có quy tắc hợp lệ.
- Nhiều đoạn code lặp lại cùng một chính sách.
- Không phân biệt được những trạng thái có ý nghĩa khác nhau.
- Không thể giải thích vì sao một giao dịch cũ được chấp nhận hoặc từ chối.
- Một cập nhật dữ liệu có thể phá vỡ invariant vì không có consistency boundary rõ.

Ví dụ, nếu `Order` chỉ có `status = "DONE"`, đội phát triển không thể biết “DONE” nghĩa là đã được chấp nhận, đã thanh toán, đã giao hay đã đóng hồ sơ. Mô hình cần những trạng thái và sự kiện phân biệt các mốc mà domain thực sự quan tâm.

Một ví dụ khác là dùng `double` để tính tiền mà không có quy tắc về currency, độ chính xác và làm tròn. Nếu số tiền có ý nghĩa tài chính, `Money` nên là một Value Object có quy tắc rõ ràng.

### Bổ sung chi tiết khi domain cần

- Tách trạng thái khi mỗi trạng thái có hành vi hoặc quyền chuyển đổi khác nhau.
- Tạo Value Object khi một giá trị có ý nghĩa và quy tắc hợp lệ riêng.
- Đưa hành vi vào Entity/Aggregate khi nó bảo vệ invariant.
- Ghi nhận Domain Event khi một sự việc có ý nghĩa và cần được diễn đạt rõ.
- Lưu snapshot khi cần bảo toàn sự thật tại thời điểm giao dịch.

## 8. Ví dụ xuyên ngữ cảnh: Product trong Catalog, Sales, Inventory và Fulfillment

Giả sử một doanh nghiệp bán một chiếc balo. Bốn context cùng quan tâm đến mặt hàng này nhưng phục vụ những mục tiêu khác nhau.

### Product Catalog: mô tả thứ khách có thể lựa chọn

Catalog có thể mô hình hóa:

```text
Product
  productId
  name
  description
  images
  category
  attributes
  variants
  publicationStatus
```

Catalog cần chi tiết về cách sản phẩm được giới thiệu, tìm kiếm và công bố. Nó có thể quản lý mô tả, hình ảnh, danh mục, màu sắc, kích thước và biến thể. Một Product có thể chưa được bán, đã ngừng công bố hoặc chỉ được hiển thị trong một số kênh.

### Sales: ghi nhận điều kiện mua đã chấp nhận

Sales có thể mô hình hóa Order Line như sau:

```text
OrderLine
  productReference
  sku
  productNameSnapshot
  quantity
  unitPriceSnapshot
  discountSnapshot
  taxTreatmentSnapshot
```

Sales cần nhận diện mặt hàng và bảo toàn điều kiện giao dịch. Tên và giá được snapshot giúp hóa đơn hoặc lịch sử đơn hàng vẫn phản ánh đúng những gì khách đã mua ngay cả khi Catalog đổi tên hoặc giá sau đó.

Sales không cần sao chép toàn bộ ảnh, nội dung SEO hay lịch sử chỉnh sửa mô tả của Catalog. Nếu khách thay đổi giỏ hàng trước khi đặt, Sales có thể truy vấn thông tin thương mại mới qua hợp đồng phù hợp, nhưng khi Order được chấp nhận thì các giá trị cần bảo toàn phải được ghi nhận theo policy.

### Inventory: quản lý số lượng theo SKU và kho

Inventory quan tâm đến:

```text
StockItem
  sku
  warehouseId
  onHandQuantity
  reservedQuantity
  availableQuantity
  reservations
```

`availableQuantity` có thể được tính theo policy từ lượng vật lý, lượng đã giữ, lượng không thể bán hoặc các điều chỉnh khác. Inventory bảo vệ invariant về reservation. Nó không cần biết Product có mô tả marketing dài bao nhiêu hay ảnh bìa nào đang được hiển thị.

### Fulfillment: chuẩn bị mặt hàng vật lý

Fulfillment có thể cần:

```text
PickItem
  sku
  barcode
  quantityToPick
  storageLocation
  dimensions
  weight
  handlingInstructions
```

Fulfillment cần nhận diện chính xác hàng cần lấy, vị trí và cách xử lý. Với một số loại hàng, hướng dẫn bảo quản hoặc đóng gói là chi tiết quan trọng. Các trường này có thể được lấy từ dữ liệu do context sở hữu hoặc được snapshot theo yêu cầu của quy trình.

### So sánh bốn mô hình

| Khía cạnh | Catalog | Sales | Inventory | Fulfillment |
|---|---|---|---|---|
| Danh tính chính | Product/Variant | Order Line và SKU tham chiếu | Stock Item theo kho | Pick Item hoặc Shipment Line |
| Mục tiêu | Giúp khách chọn hàng | Bảo toàn giao dịch mua | Quản lý lượng hàng | Lấy, đóng gói và giao |
| Giá bán | Có thể hiển thị giá hiện tại | Cần giá đã chốt | Thường không phải trách nhiệm chính | Thường không cần |
| Mô tả và hình ảnh | Quan trọng | Có thể lưu snapshot tối thiểu | Thường không cần | Có thể cần ảnh nhận diện hoặc hướng dẫn |
| Số lượng tồn | Có thể hiển thị thông tin tổng hợp | Cần biết khả năng mua theo policy | Là dữ liệu và quyết định cốt lõi | Cần số lượng phải lấy và trạng thái picking |
| Quy tắc chính | Công bố và phân loại sản phẩm | Chấp nhận giao dịch và giá | Reservation và khả dụng | Picking, packing và dispatch |

Các mô hình có thể chia sẻ mã tham chiếu như `productId` hoặc `sku`, nhưng không vì thế mà phải chia sẻ cùng một object. Mỗi context diễn giải dữ liệu theo ngôn ngữ và trách nhiệm của nó.

## 9. Chọn giữa reference, snapshot và dữ liệu được truy vấn

Một quyết định quan trọng khi chọn mức độ chi tiết là nên lưu dữ liệu của context khác theo cách nào.

### Reference: chỉ giữ định danh

Reference phù hợp khi context chỉ cần biết đối tượng liên quan để gọi một hợp đồng hoặc tra cứu thông tin khi cần.

Ví dụ, Payment có thể giữ `orderId` để biết khoản thanh toán phục vụ đơn nào. Nó không cần lưu toàn bộ Order của Sales. Reference giúp giảm trùng lặp nhưng khi truy vấn cần tính đến khả năng dữ liệu nguồn đã thay đổi hoặc không sẵn sàng.

### Snapshot: giữ giá trị tại thời điểm xảy ra

Snapshot phù hợp khi domain cần bảo toàn điều kiện hoặc bằng chứng lịch sử.

Ví dụ, Order Line lưu tên sản phẩm và giá đã chốt. Nếu Catalog đổi giá vào ngày hôm sau, lịch sử Order vẫn phải phản ánh giá lúc mua. Tương tự, địa chỉ giao hàng đã xác nhận có thể được snapshot để việc giao hàng không tự đổi theo hồ sơ địa chỉ mới của khách.

Snapshot không phải bản sao tùy tiện. Cần xác định chính xác giá trị nào phải bất biến, tại thời điểm nào được chụp và ai có quyền điều chỉnh sau đó.

### Query hoặc projection: lấy dữ liệu phục vụ đọc

Một context có thể cần hiển thị dữ liệu tổng hợp từ nhiều nguồn. Thay vì đưa toàn bộ dữ liệu đó vào domain model, hệ thống có thể dùng query hoặc read model phù hợp.

Ví dụ, màn hình chi tiết đơn hàng có thể hiển thị trạng thái thanh toán mới nhất, tiến độ giao hàng và tên sản phẩm. Đây có thể là một projection được cập nhật từ event hoặc truy vấn các context qua API. Projection phục vụ đọc; nó không tự động trở thành nguồn quyết định cho invariant của Payment, Fulfillment hay Sales.

| Cách giữ dữ liệu | Dùng khi | Rủi ro cần quản lý |
|---|---|---|
| Reference | Chỉ cần nhận diện đối tượng khác | Nguồn có thể không khả dụng hoặc thông tin đã thay đổi |
| Snapshot | Cần bảo toàn sự thật tại một thời điểm | Phải xác định thời điểm chụp và cách xử lý sửa đổi hợp lệ |
| Query/projection | Cần tổng hợp hoặc hiển thị thông tin | Dữ liệu có thể trễ và không nên dùng thay nguồn quyết định |

## 10. Phân biệt Domain Model và Read Model

Domain Model hỗ trợ hành vi và quyết định nghiệp vụ. Read Model hỗ trợ truy vấn, tìm kiếm và hiển thị. Hai mô hình có thể có cấu trúc khác nhau dù cùng lấy thông tin từ một domain.

Ví dụ, `Order` trong Sales có thể là Aggregate với các hành vi `place()`, `cancel()` và `changeShippingAddress()`. Màn hình danh sách đơn hàng lại cần một projection gồm `orderId`, `customerName`, `totalAmount`, `paymentStatus`, `shipmentStatus` và `placedAt`.

Projection có thể gộp dữ liệu từ Sales, Payment và Fulfillment để truy vấn nhanh. Nhưng nếu người dùng nhấn “Hoàn tiền”, ứng dụng cần gửi yêu cầu đến Payment Context theo hợp đồng của Payment. Không nên cập nhật trực tiếp field `paymentStatus` trong read model rồi xem đó là quyết định hoàn tiền.

Trong kiến trúc CQRS, mô hình ghi và mô hình đọc có thể được tách rõ. Tuy nhiên, không cần áp dụng CQRS phức tạp cho mọi use case. Chỉ tách khi có nhu cầu về truy vấn, hiệu năng hoặc mô hình đọc khác biệt đủ lớn.

## 11. Mức độ chi tiết thay đổi theo vòng đời và thời gian

Một số khái niệm cần mô hình hóa chi tiết hơn khi thời gian làm thay đổi ý nghĩa của dữ liệu.

Ví dụ:

- Giá sản phẩm hiện tại khác giá đã chốt trong Order.
- Địa chỉ hiện tại của khách khác địa chỉ được dùng cho một Shipment cũ.
- Hạn mức tín dụng hiện tại khác hạn mức có hiệu lực tại thời điểm khoản vay được phê duyệt.
- Chính sách hoàn tiền mới có thể khác chính sách áp dụng cho giao dịch cũ.

Khi cần giải thích lịch sử, mô hình có thể phải lưu giá trị snapshot, phiên bản chính sách hoặc thời điểm hiệu lực. Nếu chỉ giữ giá trị hiện tại, hệ thống có thể không tái dựng được vì sao quyết định trong quá khứ được đưa ra.

Hãy hỏi:

- Dữ liệu có thể thay đổi sau khi giao dịch được xác nhận không?
- Khi thay đổi, giao dịch cũ có cần giữ nguyên cách hiểu ban đầu không?
- Có cần biết chính sách nào có hiệu lực tại thời điểm ra quyết định không?
- Có cần lưu lịch sử thay đổi để kiểm toán hoặc giải thích không?

Không phải field nào cũng cần versioning hoặc lịch sử đầy đủ. Chỉ bổ sung khi có yêu cầu nghiệp vụ, pháp lý hoặc vận hành cụ thể.

## 12. Cách chọn mức độ chi tiết theo từng context

Có thể áp dụng quy trình sau khi bắt đầu mô hình hóa một context.

### Bước 1: Xác định trách nhiệm của context

Viết một câu mô tả context chịu trách nhiệm cho năng lực nào và những quyết định nào thuộc về nó. Ví dụ: Inventory chịu trách nhiệm về số lượng hàng có thể bán và việc giữ hàng theo kho.

### Bước 2: Liệt kê use case quan trọng

Chọn những hành vi cần được hỗ trợ. Với Inventory, có thể là nhập hàng, điều chỉnh tồn, reserve, release reservation và kiểm kê.

### Bước 3: Xác định invariant và các trường hợp ngoại lệ

Với mỗi use case, hỏi điều gì phải luôn đúng và tình huống nào làm thay đổi kết quả. Ví dụ, reserve có thể bị từ chối khi số lượng khả dụng không đủ hoặc SKU không được phép bán tại kho đó.

### Bước 4: Chọn thông tin cần thiết

Liệt kê dữ liệu trực tiếp tham gia vào quyết định. Phân biệt dữ liệu domain sở hữu, reference từ context khác, snapshot cần bảo toàn và dữ liệu chỉ phục vụ hiển thị.

### Bước 5: Chọn mức độ phân biệt

Nếu hai trường hợp có hành vi, quyền hoặc vòng đời khác nhau, mô hình có thể cần phân biệt chúng. Nếu khác biệt không ảnh hưởng đến quyết định nào trong context, chưa chắc cần tạo kiểu hoặc trạng thái riêng.

### Bước 6: Kiểm tra bằng ví dụ thực tế

Đưa mô hình vào một số tình huống bình thường và ngoại lệ. Nhờ chuyên gia nghiệp vụ xác nhận rằng mô hình diễn đạt đúng sự việc và kết quả.

### Bước 7: Kiểm tra ranh giới với context khác

Xác định dữ liệu nào được trao đổi, cách chuyển đổi và ai sở hữu quyết định. Nếu mô hình phải biết quá nhiều chi tiết nội bộ của context khác, hãy xem lại contract hoặc boundary.

### Bước 8: Điều chỉnh theo bằng chứng

Khi có use case mới hoặc quy tắc thay đổi, xem xét mô hình có cần thêm chi tiết hay có phần nào đã trở nên dư thừa. Không nên giữ mô hình cũ chỉ vì nó đã được triển khai.

## 13. Một bảng quyết định thực dụng

Khi cân nhắc thêm một field, Entity, Value Object hoặc trạng thái, hãy dùng bảng câu hỏi sau:

| Câu hỏi | Nếu câu trả lời là Có | Nếu câu trả lời là Không |
|---|---|---|
| Có tham gia vào quyết định nghiệp vụ của context không? | Đưa vào mô hình hoặc hợp đồng cần thiết | Cân nhắc để ở read model hoặc context sở hữu |
| Có giúp bảo vệ invariant không? | Mô hình hóa rõ và kiểm tra trong hành vi | Không cần đưa vào Aggregate chỉ vì dữ liệu tồn tại |
| Có cần bảo toàn giá trị lịch sử không? | Cân nhắc snapshot hoặc version | Có thể dùng reference/query nếu phù hợp |
| Có vòng đời hoặc quy tắc riêng không? | Cân nhắc khái niệm hoặc kiểu riêng | Có thể giữ như thuộc tính nếu không có ý nghĩa độc lập |
| Context khác có cần dữ liệu này không? | Thiết kế contract tối thiểu và rõ nghĩa | Giữ nội bộ context |
| Có use case thực tế sử dụng không? | Ghi nhận use case và kiểm chứng | Trì hoãn đến khi có bằng chứng |

Bảng này là công cụ đặt câu hỏi, không phải thuật toán tự động. Một field có thể không tham gia quyết định hiện tại nhưng cần thiết cho audit hoặc yêu cầu pháp lý; khi đó phải ghi rõ lý do và owner.

## 14. Ví dụ Java: giữ Money có ý nghĩa trong Sales

Giả sử Sales cần lưu giá đã chốt trên Order Line. Dùng một kiểu số nguyên thủy cho amount và một chuỗi currency có thể đủ về mặt lưu trữ, nhưng dễ để logic tính tiền rải rác trong nhiều nơi.

Một Value Object `Money` có thể gom ý nghĩa và quy tắc:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Currency;
import java.util.Objects;

public record Money(BigDecimal amount, Currency currency) {
    public Money {
        Objects.requireNonNull(amount);
        Objects.requireNonNull(currency);

        int fractionDigits = currency.getDefaultFractionDigits();
        if (fractionDigits >= 0) {
            amount = amount.setScale(fractionDigits, RoundingMode.UNNECESSARY);
        }
    }

    public Money add(Money other) {
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }
}
```

Đây chỉ là ví dụ đơn giản. Quy tắc scale, rounding, đơn vị tiền tệ và cách cộng trừ phải phù hợp với domain và loại tiền được hỗ trợ. Điểm quan trọng là Sales biểu diễn tiền như một khái niệm có ý nghĩa, thay vì để mỗi nơi tự quyết định cách xử lý.

Trong Inventory, `Money` có thể không cần xuất hiện trong Aggregate quản lý reservation nếu việc giữ hàng không phụ thuộc giá. Một báo cáo tồn kho có thể hiển thị giá trị hàng tồn qua projection khác. Cùng một sản phẩm không có nghĩa mọi context phải chứa cùng một Value Object.

## 15. Những yếu tố ảnh hưởng đến mức độ chi tiết

Không có một mức chi tiết cố định cho mọi context. Một số yếu tố cần cân nhắc:

**Độ phức tạp nghiệp vụ.** Nhiều quy tắc, ngoại lệ và trạng thái có thể cần mô hình chi tiết hơn.

**Tần suất thay đổi.** Phần nghiệp vụ thay đổi thường xuyên cần mô hình dễ hiểu và dễ điều chỉnh. Đừng đóng cứng các chính sách biến động vào cấu trúc dữ liệu khó sửa.

**Rủi ro của quyết định.** Quyết định ảnh hưởng đến tiền, quyền lợi khách hàng hoặc tuân thủ thường cần dữ liệu, lịch sử và lý do rõ hơn.

**Consistency boundary.** Các invariant cần được bảo vệ cùng nhau có thể yêu cầu Aggregate hoặc mô hình có trách nhiệm rõ. Không nên mở rộng Aggregate chỉ để gom nhiều field.

**Nhu cầu đọc.** Màn hình, báo cáo và tìm kiếm có thể cần projection giàu thông tin hơn domain model ghi.

**Quyền sở hữu giữa các nhóm.** Context do các nhóm khác nhau sở hữu thường cần contract rõ và dữ liệu trao đổi có giới hạn.

**Thời gian và audit.** Nếu cần giải thích quyết định cũ, có thể phải giữ snapshot, version hoặc event history.

**Chi phí vận hành.** Mỗi kiểu dữ liệu, abstraction và quy tắc mới đều có chi phí triển khai, kiểm thử và bảo trì. Chi tiết phải mang lại giá trị tương xứng.

## 16. Các sai lầm thường gặp

**Dùng một model chung cho mọi context.** Điều này thường làm mô hình phình to và khiến các nhóm phụ thuộc vào chi tiết không liên quan. Hãy để mỗi context biểu diễn khái niệm theo trách nhiệm riêng.

**Đồng nhất mức chi tiết với số lượng field.** Nhiều field không có nghĩa mô hình sâu. Một Value Object nhỏ như `Money` có thể chứa quy tắc quan trọng hơn một DTO với hàng chục thuộc tính.

**Đưa dữ liệu hiển thị vào Aggregate.** Mô tả dài, ảnh hoặc thông tin SEO có thể phù hợp với read model của Catalog, nhưng không nhất thiết thuộc Aggregate bảo vệ quy tắc bán hàng.

**Đưa quy tắc ra ngoài domain model.** Nếu một invariant quan trọng chỉ tồn tại trong controller hoặc script, các use case khác có thể bỏ qua nó.

**Dùng dữ liệu hiện tại để giải thích giao dịch cũ.** Giá, địa chỉ hoặc chính sách có thể thay đổi. Khi domain cần lịch sử, hãy lưu snapshot hoặc phiên bản có chủ đích.

**Dùng projection để ra quyết định ghi.** Read model có thể trễ hoặc tổng hợp. Các quyết định cần bảo vệ invariant phải được thực hiện bởi context sở hữu dữ liệu và quy tắc đó.

**Tạo kiểu riêng cho mọi field.** Value Object hữu ích khi giá trị có ngữ nghĩa hoặc quy tắc hợp lệ riêng. Không cần biến mọi chuỗi thành một class nếu điều đó không giúp mô hình rõ hơn.

**Tối ưu mô hình cho một màn hình duy nhất.** Màn hình có thể thay đổi nhanh. Hãy cân nhắc read model riêng thay vì làm domain model phụ thuộc vào cấu trúc giao diện.

## 17. Bài tập tự kiểm tra

Một doanh nghiệp cho thuê xe có ba Bounded Context: Fleet Management, Booking và Maintenance. Cả ba cùng quan tâm đến một chiếc xe.

Hãy đề xuất mức độ chi tiết của mô hình `Vehicle` cho từng context và giải thích:

1. Fleet Management cần quản lý biển số, dòng xe, năm sản xuất, tình trạng sở hữu và trạng thái khai thác như thế nào?
2. Booking cần biết xe có thể được đặt trong khoảng thời gian nào, loại xe, giá thuê đã chốt và điều kiện bàn giao nào?
3. Maintenance cần theo dõi số km, lịch bảo dưỡng, hạng mục sửa chữa, phụ tùng và lịch sử hỏng hóc nào?
4. Khi xe được đưa vào bảo dưỡng, context nào quyết định xe không còn khả dụng để đặt?
5. Booking nên giữ tham chiếu đến Vehicle hay snapshot những thông tin nào tại thời điểm xác nhận đặt xe?
6. Màn hình tra cứu xe có thể cần một read model tổng hợp từ cả ba context không?

Gợi ý:

| Context | Mô hình nên tập trung vào | Ví dụ chi tiết |
|---|---|---|
| Fleet Management | Danh tính và trạng thái khai thác của xe | `VehicleId`, biển số, loại xe, trạng thái đội xe, chi nhánh |
| Booking | Điều kiện thuê và cam kết với khách | `VehicleReference`, loại xe đã đặt, giá thuê snapshot, thời gian thuê, điều kiện bàn giao |
| Maintenance | Tình trạng kỹ thuật và lịch sử bảo dưỡng | số km, lịch bảo dưỡng, Work Order, phụ tùng, kết quả kiểm tra |

Fleet Management có thể sở hữu trạng thái xe có được đưa vào khai thác hay không; Maintenance sở hữu quyết định kỹ thuật về công việc bảo dưỡng. Booking cần nhận thông tin khả dụng qua hợp đồng rõ ràng và giữ lại các điều kiện thuê đã chốt. Cách phân chia cuối cùng phải được xác nhận với quy trình thật của doanh nghiệp.

## Kết luận

Mức độ chi tiết của mô hình phải phù hợp với trách nhiệm của Bounded Context, use case, quyết định và invariant mà context bảo vệ. Cùng một khái niệm trong thế giới thực có thể được biểu diễn khác nhau trong Catalog, Sales, Inventory hoặc Fulfillment vì mỗi nơi cần trả lời những câu hỏi khác nhau.

Hãy tránh cả hai cực: mô hình quá chi tiết làm tăng phụ thuộc và chi phí duy trì; mô hình quá sơ sài khiến quy tắc bị phân tán và khó bảo vệ. Phân biệt domain model với read model, chọn reference hay snapshot theo nhu cầu lịch sử, và chỉ đưa vào mô hình những chi tiết có lý do rõ ràng. Khi domain hoặc use case thay đổi, hãy kiểm chứng lại mức chi tiết thay vì mặc định mô hình hiện tại luôn phù hợp.
