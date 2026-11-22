# Lặp dữ liệu phục vụ đọc và xác định nguồn dữ liệu chuẩn

Trong một ứng dụng thương mại điện tử, người dùng thường muốn mở nhanh trang chi tiết đơn hàng, xem các đơn gần nhất, lọc những đơn đang chờ giao và tìm những sản phẩm đã mua. Mỗi màn hình có **đầu vào, điều kiện lọc và thứ tự đọc khác nhau**. Nếu chỉ giữ một bản ghi chuẩn rồi thực hiện nhiều phép nối hoặc quét mọi dữ liệu để dựng từng màn hình, ứng dụng NoSQL có thể gặp độ trễ lớn, đặc biệt khi dữ liệu được chia trên nhiều node.

Một giải pháp quen thuộc là **lặp có chủ đích một số dữ liệu** (*denormalization/duplication*) ở những cấu trúc được tối ưu cho từng đường đọc: tên sản phẩm có mặt trong giỏ hàng, thông tin đơn hàng có mặt trong danh sách của khách, trạng thái đơn có mặt trong bảng điều phối giao hàng.

Nhưng nếu thông tin được lưu ở nhiều nơi, câu hỏi trở nên khó hơn: **khi hai bản sao khác nhau, bản nào đúng?** Khi giá sản phẩm thay đổi, lịch sử đơn hàng có phải thay theo không? Khi đơn đã giao, điều gì ngăn nó còn nằm trong danh sách “chờ giao”? Nếu một bản chiếu đọc bị mất, làm sao xây dựng lại mà không tạo dữ liệu sai?

Bài học này tập trung vào hai nguyên tắc bổ sung cho nhau:

1. **Lặp dữ liệu để phục vụ đọc:** lưu một số thuộc tính ở nhiều vị trí theo mẫu truy vấn quan trọng, nhằm giảm số lượt đọc, truy vấn chéo phân vùng và công việc kết hợp dữ liệu.
2. **Xác định nguồn dữ liệu chuẩn:** xác định chủ sở hữu của từng sự kiện/trạng thái nghiệp vụ; từ đó biết nơi nào có quyền quyết định giá trị đúng, nơi nào chỉ là bản chiếu, snapshot hoặc cache.

Không phải mọi bản sao đều cần giống nhau theo thời gian. Một **giá sản phẩm hiện hành** và **giá đã chốt lúc mua** là hai dữ kiện khác nhau dù cùng tên trường `price`. Phân biệt được chúng là nền tảng để lặp dữ liệu mà không phá vỡ tính đúng đắn.

## 1. Từ dữ liệu quan hệ tới dữ liệu tối ưu theo cách đọc

Trong thiết kế quan hệ được chuẩn hóa, thông tin sản phẩm và khách hàng thường chỉ nằm ở bảng sở hữu; đơn hàng dùng khóa ngoại để tham chiếu. Một truy vấn chi tiết đơn có thể cần nối `orders`, `order_lines`, `products` và `customers`.

Trong nhiều hệ NoSQL, đặc biệt là **key–value**, **document** và **wide-column**, một số phép join không có, bị giới hạn hoặc có chi phí lớn khi chạy xuyên partition. Vì vậy người thiết kế thường đưa vào bản ghi đọc **những thông tin được sử dụng cùng nhau**.

~~~mermaid
flowchart LR
    O["Order O900"] -->|tham chiếu| C["Customer U42"]
    O -->|chứa| L["OrderLine P101 × 2"]
    L -->|tham chiếu| P["Product P101"]
    O -->|chiếu sang| H["Customer order history"]
    O -->|chiếu sang| S["Shop shipping queue"]
    P -->|chiếu sang| X["Search/catalog view"]
~~~

Hai cách nhìn:

| Thiết kế ưu tiên nguồn chuẩn | Thiết kế ưu tiên đọc |
| --- | --- |
| Mỗi dữ kiện nghiệp vụ có nơi sở hữu rõ ràng | Một số dữ kiện được sao chép vào nhiều cấu trúc |
| Cập nhật một nơi dễ kiểm soát | Đọc nhanh khi đúng đường truy cập |
| Có thể cần nhiều lần đọc và kết hợp dữ liệu | Có thể tránh nhiều join hoặc quét |
| Ít bản sao cần đồng bộ | Phải duy trì bản chiếu khi dữ liệu đổi |
| Phù hợp cho quyết định ghi nghiệp vụ | Phù hợp cho màn hình, báo cáo hoặc truy vấn lặp lại |

**Đây không phải lựa chọn “hoặc chuẩn hóa, hoặc lặp dữ liệu” cho toàn hệ thống.** Một thiết kế thực tế thường giữ **bản chuẩn có quyền quyết định** cho từng dữ kiện và tạo **một số bản đọc phụ có thể tái tạo**.

### 1.1. “Denormalization” không có nghĩa sao chép toàn bộ đối tượng

Giả sử màn hình danh sách đơn chỉ cần:

~~~text
orderId, createdAt, status, totalVnd, itemCount
~~~

Không cần sao chép toàn bộ địa chỉ giao hàng, lịch sử thanh toán, thông tin định danh nhạy cảm hay mọi dòng sản phẩm vào từng hàng danh sách. Một **projection nhỏ, đúng mục đích** thường rẻ hơn và dễ bảo vệ hơn một bản sao nguyên khối.

Thêm một trường vào projection phải có lý do: giảm một lần đọc bổ sung, tránh truy vấn khác hoặc phục vụ một bộ lọc/sắp xếp quan trọng.

## 2. Bài toán xuyên suốt: cửa hàng và đơn hàng

Một nền tảng có các dịch vụ/nhóm dữ liệu:

- **Catalog:** sản phẩm, tên hiển thị hiện tại, giá niêm yết, trạng thái bán.
- **Customer:** hồ sơ và các thông tin liên hệ hiện tại của khách.
- **Orders:** đơn hàng đã được tạo, những dòng hàng đã chốt, số tiền theo điều khoản giao dịch, trạng thái xử lý đơn.
- **Payments:** giao dịch thanh toán, hoàn tiền, trạng thái xác nhận của nhà cung cấp.
- **Shipping:** phiếu giao, hãng vận chuyển và thông tin giao hàng.

Ví dụ một sản phẩm:

~~~json
{
  "productId": "P101",
  "shopId": "shop-12",
  "name": "Tai nghe Bluetooth X",
  "currentPriceVnd": 550000,
  "catalogVersion": 8,
  "active": true
}
~~~

Khách U42 tạo đơn O900 mua **2 chiếc P101** khi giá chốt là **500.000 VND/chiếc**. Một tuần sau Catalog đổi giá hiện hành thành **550.000 VND/chiếc**. Bản ghi đơn có thể lưu:

~~~json
{
  "tenantId": "merchant-a",
  "orderId": "O900",
  "customerId": "U42",
  "shopId": "shop-12",
  "createdAt": "2026-11-14T09:30:00Z",
  "status": "PAID",
  "version": 3,
  "lines": [
    {
      "productId": "P101",
      "productNameAtPurchase": "Tai nghe Bluetooth X",
      "unitPriceAtPurchaseVnd": 500000,
      "quantity": 2,
      "lineTotalVnd": 1000000
    }
  ],
  "totalVnd": 1000000
}
~~~

Trong ví dụ, `totalVnd` được giả định bằng tổng dòng hàng và **chưa có phí giao hàng, thuế hoặc chiết khấu**. Khi nghiệp vụ có các khoản đó, snapshot của đơn phải lưu đủ dữ kiện để tái hiện tổng tiền đã chốt.

### 2.1. Các đường đọc cần phục vụ

| Mã | Yêu cầu đọc | Khóa đầu vào thường có | Thứ tự/đầu ra |
| --- | --- | --- | --- |
| Q1 | Chi tiết đơn O900 | `tenantId + orderId` | Một đơn, gồm các dòng hàng |
| Q2 | 20 đơn mới nhất của U42 | `tenantId + customerId` | `createdAt DESC` |
| Q3 | Các đơn READY_TO_SHIP của shop-12 | `tenantId + shopId` | Mới nhất trước, có phân trang |
| Q4 | Danh mục sản phẩm đang bán | `shopId`, nhóm sản phẩm | Giá/tên **hiện tại** |
| Q5 | Hiển thị lịch sử thanh toán của O900 | `orderId` hoặc `paymentId` | Những giao dịch có nguồn gốc rõ ràng |

Q1–Q5 không cùng một đường truy cập. **Một bảng theo orderId** không tự trả nhanh top-20 theo customer hoặc shop. Ngược lại, một bảng theo customer không phải nguồn đáng tin cậy để thực hiện lệnh thanh toán.

## 3. Nguồn dữ liệu chuẩn (source of truth) là gì?

**Nguồn dữ liệu chuẩn** là nơi có thẩm quyền quyết định giá trị hiện hành hoặc sự kiện đã xác nhận cho **một dữ kiện nghiệp vụ cụ thể**. Khi hệ thống có nhiều bản sao và phát hiện bất đồng, nguồn này được dùng để xác định trạng thái đúng, sửa bản chiếu và giải quyết xung đột.

Không nhất thiết toàn công ty chỉ có **một database chuẩn**. Hệ thống có thể có nhiều miền sở hữu, nhưng mỗi **loại dữ kiện** phải có chủ sở hữu rõ ràng.

| Dữ kiện cần hỏi | Nguồn có quyền quyết định | Bản sao/phần chiếu |
| --- | --- | --- |
| Tên, giá niêm yết sản phẩm hiện tại | Catalog | Trang tìm kiếm, cache sản phẩm |
| Giá đã chốt của dòng hàng O900 | Orders, theo điều khoản đơn | Chi tiết đơn, hóa đơn/báo cáo đã phát hành theo chính sách |
| Trạng thái xử lý đơn O900 | Orders | Danh sách theo khách, hàng chờ giao |
| Thanh toán PAY700 đã được provider xác nhận? | Payments/ledger và cơ chế đối soát provider | Tóm tắt trạng thái trả tiền trên đơn |
| Hãng vận chuyển và mã vận đơn | Shipping | Trang theo dõi đơn, thông báo |
| Tên khách đang dùng trên hồ sơ | Customer | Cache, danh sách khách |
| Người nhận và địa chỉ giao đã chốt cho O900 | Orders/Shipping theo quy trình chốt địa chỉ | Phiếu giao, màn hình chi tiết |

**“Nguồn chuẩn” không tự động đồng nghĩa bản ghi có timestamp lớn nhất.** Thời gian trên các máy có thể lệch; sự kiện đến muộn, được retry hoặc nhập lại. Quyền cập nhật, version, transaction và quy tắc trạng thái nghiệp vụ mới quyết định dữ kiện nào được chấp nhận.

### 3.1. Phân biệt quyền sở hữu và nơi hiển thị

Một màn hình Orders có thể hiển thị:

~~~text
Order.status = PAID
Payment.displayStatus = CAPTURED
Shipping.trackingState = IN_TRANSIT
~~~

Màn hình đó **không trở thành chủ sở hữu của Payment hoặc Shipping**. Nó chỉ là điểm tổng hợp để người dùng đọc dễ hơn. Nếu payment gateway phản hồi hoàn tiền thành công, hệ Payment phải xác nhận và ghi nhận giao dịch; sau đó trạng thái hiển thị ở Orders có thể được cập nhật qua một sự kiện/luồng đồng bộ.

### 3.2. Dữ liệu hiện hành và snapshot lịch sử là hai dữ kiện khác nhau

Đây là khác biệt đặc biệt quan trọng:

~~~text
Catalog.currentPrice(P101) = 550.000 VND
OrderLine.unitPriceAtPurchase(O900, P101) = 500.000 VND
~~~

Cả hai đều đúng, **không phải hai bản sao đang bị lệch**. Chúng mô tả hai thời điểm và hai ý nghĩa:

- `currentPrice` là dữ liệu hiện hành, thay đổi khi Catalog điều chỉnh giá.
- `unitPriceAtPurchase` là **snapshot đã chốt theo giao dịch**, giữ lại để tái hiện điều kiện mua của O900.

Nếu “đồng bộ” giá mới vào đơn cũ, hệ thống có thể làm sai tổng tiền, báo cáo và trải nghiệm đối soát. Những trường dạng `AtPurchase`, `AtCheckout`, `AtIssue` phải được xem là **giá trị lịch sử có chủ sở hữu**, không phải cache cần được làm mới.

### 3.3. Sự kiện đã xác nhận và bản tổng hợp có thể khác nhau

Một đơn có thể hiển thị `paymentStatus: PAID` theo projection. Dữ kiện tài chính chi tiết có thể được ghi bằng các giao dịch và bút toán trong Payments. Nếu số tiền hoặc trạng thái giữa hai nơi không khớp, quy trình phải đối chiếu với **các bản ghi thanh toán có thẩm quyền**, không kết luận chỉ từ trường hiển thị trên order.

Với dữ liệu có yêu cầu kiểm toán, có thể cần thêm **lịch sử sự kiện bất biến hoặc ledger** bên cạnh trạng thái hiện tại. Trạng thái hiện tại là một cách nhìn, còn lịch sử xác nhận là căn cứ giải thích vì sao nó trở thành trạng thái đó.

## 4. Ba kiểu lặp dữ liệu cần phân biệt

Cùng là “copy” nhưng mục đích và quy tắc cập nhật không giống nhau:

| Kiểu dữ liệu | Ví dụ | Có cập nhật theo nguồn mới? | Mất bản sao thì sao? |
| --- | --- | --- | --- |
| **Projection/read model** | `orders_by_customer_month` | Có, theo sự kiện/phiên bản tương ứng | Có thể tái tạo từ nguồn và lịch sử thay đổi |
| **Cache** | `product:P101` trong Redis | Có, theo TTL/invalidation/refresh | Cache miss rồi đọc lại nguồn |
| **Snapshot nghiệp vụ** | `unitPriceAtPurchaseVnd` của O900 | Thường **không tự cập nhật** khi Catalog đổi giá | Phải giữ theo chính sách lưu trữ của giao dịch |

### 4.1. Projection

Projection lưu **một cách nhìn khác của cùng dữ kiện hiện hành**: có thể chỉ chứa vài trường, sắp xếp theo khóa khác và được cập nhật từ nguồn chuẩn. Nếu nguồn có thể tái dựng đầy đủ, projection về nguyên tắc là dữ liệu phụ có thể rebuild.

### 4.2. Cache

Cache tối ưu truy cập lặp lại và có thể cho phép hết hạn. Không nên dùng cache có TTL ngắn làm **nguồn duy nhất** cho trạng thái đơn hoặc bằng chứng thanh toán. Một cache bị xóa không được làm biến mất dữ kiện nghiệp vụ.

### 4.3. Snapshot

Snapshot lưu **sự thật tại một thời điểm hoặc thời điểm chốt**. Các trường trên dòng đơn, bảng giá đã ký, địa chỉ giao đã xác nhận, nội dung hóa đơn hoặc số thuế tại giao dịch là ví dụ thường cần snapshot, tùy quy định sản phẩm.

Không nên đặt tên chung chung `price` ở mọi nơi. Tên `currentPrice`, `priceAtPurchase` và `discountAmountApplied` giúp người đọc biết cái nào được cập nhật, cái nào phải giữ nguyên.

## 5. Quy trình quyết định có nên lặp một dữ kiện

Không phải mọi dữ liệu đều đáng lặp. Với mỗi truy vấn, đặt các câu hỏi:

1. **Truy vấn có tần suất cao hoặc SLA nghiêm ngặt không?** Một màn hình hiếm dùng có thể chấp nhận đọc bổ sung.
2. **Ứng dụng biết khóa nào?** `orderId`, `customerId`, `shopId`, khoảng thời gian hay bộ lọc trạng thái?
3. **Nếu không lặp, phải làm bao nhiêu lần đọc?** Có fan-out qua nhiều partition/node hay quét lượng lớn bản ghi không?
4. **Dữ kiện thay đổi thường xuyên không?** Giá trị biến động mỗi giây sẽ tốn chi phí đồng bộ khác dữ kiện gần như bất biến.
5. **Cho phép dữ liệu trễ bao lâu?** Màn hình báo cáo khác với thao tác duyệt giao tiền.
6. **Bản sao lưu những trường nào?** Chỉ sao chép đúng dữ liệu cần đọc và lọc.
7. **Có thể xây lại bản sao từ nguồn không?** Nếu không, có thể nó đang giữ dữ kiện chuẩn mà chưa được thừa nhận.
8. **Ai chịu trách nhiệm sửa lệch?** Nếu không có owner/worker/metric, sự lặp sẽ tích tụ dữ liệu cũ.

Một cách quyết định:

~~~mermaid
flowchart TD
    A["Phát sinh nhu cầu đọc mới"] --> B{"Đường đọc hiện tại đạt SLA?"}
    B -->|Có| C["Giữ cấu trúc, không lặp vô cớ"]
    B -->|Không| D{"Thêm index đủ đáp ứng?"}
    D -->|Có| E["Tạo index, đo read/write cost"]
    D -->|Không| F{"Nhu cầu dữ liệu lịch sử hay hiện hành?"}
    F -->|Lịch sử đã chốt| G["Snapshot nghiệp vụ tại thời điểm chốt"]
    F -->|Hiện hành| H["Projection / cache có đồng bộ"]
    E --> I["Kiểm tra độ đúng, quyền và chi phí"]
    G --> I
    H --> I
~~~

**Mục tiêu không phải loại bỏ mọi lần đọc bổ sung**, mà là chọn cách đơn giản nhất đáp ứng đúng hợp đồng truy vấn và mức tải dự kiến.

## 6. Thiết kế read model theo khách hàng

Q2 yêu cầu lấy 20 đơn mới nhất của U42. Nếu chỉ có `orders_by_id`, ứng dụng không biết trước orderId của 20 đơn đó. Với wide-column/Cassandra, ta thường tạo bảng riêng định vị theo khách và khoảng thời gian.

~~~sql
CREATE TABLE orders_by_id (
    tenant_id text,
    order_id text,
    customer_id text,
    shop_id text,
    created_at timestamp,
    status text,
    total_vnd bigint,
    version bigint,
    PRIMARY KEY ((tenant_id, order_id))
);

CREATE TABLE orders_by_customer_month (
    tenant_id text,
    customer_id text,
    month_bucket text,
    created_at timestamp,
    order_id text,
    shop_id text,
    status text,
    total_vnd bigint,
    version bigint,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

`orders_by_id` là bản chuẩn cho trạng thái Order trong phạm vi ví dụ. `orders_by_customer_month` là **bản chiếu phục vụ đọc**; nó sao chép `status`, `total_vnd` và một số trường danh sách nhưng không quyết định chuyển trạng thái nghiệp vụ.

Truy vấn:

~~~sql
SELECT order_id, shop_id, created_at, status, total_vnd
FROM orders_by_customer_month
WHERE tenant_id = 'merchant-a'
  AND customer_id = 'U42'
  AND month_bucket = '2026-11'
LIMIT 20;
~~~

Vì dữ liệu trong partition được lưu theo `created_at DESC`, truy vấn đọc trực tiếp đúng thứ tự. Nếu tháng hiện tại có ít hơn 20 đơn, API có thể đọc tháng trước và nối kết quả theo thứ tự thời gian.

### 6.1. Tại sao dùng bucket tháng?

Nếu mọi đơn của U42 nhiều năm đều nằm trong một partition, partition có thể lớn dần và gây chi phí đọc/bảo trì. `month_bucket` hạn chế số hàng logic trong một partition, đổi lại việc đọc nhiều tháng đòi hỏi nhiều truy vấn.

Khoảng bucket phù hợp phải được chọn theo **số đơn của khách hàng hoạt động mạnh nhất**, kích thước mỗi hàng và đường đọc phổ biến; không có bucket “tháng” tối ưu cho mọi nghiệp vụ.

### 6.2. Vì sao có thêm `order_id` trong clustering key?

Hai đơn có thể có cùng `created_at` ở độ chính xác timestamp đang dùng. Nếu chỉ khóa theo `created_at`, hai đơn có thể đụng cùng khóa chính; trong Cassandra, ghi bằng cùng primary key thường mang ngữ nghĩa upsert.

`order_id` giúp phân biệt hàng và tạo thứ tự phụ xác định. Khi phân trang, cursor cũng cần ghi nhớ cả thời gian và ID để không bỏ qua/đếm trùng các đơn cùng timestamp.

### 6.3. Không cần sao chép mọi trường của Order

Chi tiết địa chỉ, mã voucher, số điện thoại, lịch sử chuyển trạng thái và các dòng hàng có thể không cần ở danh sách Q2. API lấy chúng khi người dùng mở đơn cụ thể qua `orders_by_id` hoặc nguồn sở hữu tương ứng.

Việc chỉ lặp **dữ kiện phục vụ danh sách** giảm write amplification, dung lượng và rủi ro dữ liệu nhạy cảm bị lưu ở quá nhiều nơi.

## 7. Thiết kế read model theo trạng thái vận hành

Q3 cần “các đơn `READY_TO_SHIP` của shop-12, mới nhất trước”. Bảng theo khách không giải quyết được vì một shop có nhiều khách. Có thể tạo bảng chỉ chứa các đơn hiện đang ở trạng thái này:

~~~sql
CREATE TABLE ready_orders_by_shop_day (
    tenant_id text,
    shop_id text,
    day_bucket date,
    created_at timestamp,
    order_id text,
    customer_id text,
    total_vnd bigint,
    source_version bigint,
    PRIMARY KEY (
        (tenant_id, shop_id, day_bucket),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Ở bảng này, việc một đơn **có hàng** nghĩa là read model tin đơn hiện đang READY. Khi trạng thái Orders chuyển từ PAID → READY, worker thêm hàng; khi chuyển READY → SHIPPED/CANCELLED, worker xóa hàng.

~~~text
Order O900 thay đổi trạng thái
       |
       v
Orders: ghi và xác nhận transition
       |
       v
Event / change log
       |
       +--> orders_by_customer_month: cập nhật status
       |
       +--> ready_orders_by_shop_day:
                  READY? thêm/cập nhật
                  không READY? xóa bản chiếu cũ
~~~

### 7.1. Xóa khỏi danh sách không có nghĩa xóa Order

Khi O900 chuyển SHIPPED, cần xóa **hàng trong danh sách READY**, nhưng phải **giữ bản ghi đơn gốc**. Một bảng read model có thể liên tục thêm/xóa theo trạng thái, còn nguồn sự thật giữ vòng đời nghiệp vụ theo chính sách lưu trữ.

### 7.2. Cần biết khóa chiếu cũ khi thay đổi

Nếu `shopId`, `createdAt` hoặc bucket có thể đổi, projection phải biết **partition/clustering key cũ** để xóa đúng hàng. Chỉ có trạng thái mới và orderId chưa chắc đủ để tính vị trí cũ.

Có thể giữ key chiếu được xác định từ Order, mang thông tin trước/sau trong event, hoặc lưu bản ghi quản lý tiến độ projector; lựa chọn phụ thuộc cách bảo đảm xử lý đúng khi retry và đảo thứ tự.

### 7.3. Chi phí của bảng “chỉ chứa trạng thái hiện hành”

Bảng sparse này giảm số hàng cần đọc, nhưng nếu đơn chuyển vào/ra READY rất nhanh sẽ phát sinh nhiều `INSERT` và `DELETE`. Trong Cassandra, xóa có thể tạo tombstone, ảnh hưởng tới truy vấn và compaction.

Nếu workload cập nhật trạng thái quá dày, cần đo chi phí projection và cân nhắc index, cách bucket khác hoặc engine tìm kiếm phù hợp; không phải cứ lặp dữ liệu là rẻ.

## 8. Embedded document: dữ liệu đọc cùng nhau trong một đối tượng

Với document database, một lựa chọn khác là **nhúng dữ liệu liên quan vào cùng document**, giúp lấy chi tiết một đơn trong một lượt đọc.

Ví dụ minh họa MongoDB:

~~~javascript
db.orders.insertOne({
  _id: "merchant-a#O900",
  tenantId: "merchant-a",
  orderId: "O900",
  customerId: "U42",
  status: "PAID",
  version: 3,
  createdAt: ISODate("2026-11-14T09:30:00Z"),
  lines: [
    {
      productId: "P101",
      productNameAtPurchase: "Tai nghe Bluetooth X",
      quantity: 2,
      unitPriceAtPurchaseVnd: 500000
    }
  ],
  totalVnd: 1000000
});
~~~

Tham chiếu tới `productId` vẫn có, nhưng dòng đơn giữ **snapshot giao dịch** để hiển thị đúng tại thời điểm mua. Đây là một lựa chọn thiết kế mạnh khi số dòng hàng trên đơn **có giới hạn hợp lý** và chúng thường được đọc cùng đơn.

### 8.1. Khi nào nên nhúng?

Nhúng thường phù hợp nếu:

- Dữ liệu con có vòng đời gắn chặt với dữ liệu cha.
- Số phần tử con được giới hạn hoặc tăng có thể kiểm soát.
- Đọc cha và con cùng lúc là đường truy cập thường xuyên.
- Cập nhật trong cùng document phù hợp với yêu cầu nguyên tử của engine.
- Con không cần được tìm kiếm độc lập theo một đường truy cập hoàn toàn khác quá thường xuyên.

Ngược lại, không nên nhúng một **danh sách tất cả đơn hàng của khách** vào một document khách hàng nếu số đơn có thể tăng vô hạn, gây document lớn, cạnh tranh cập nhật và khó phân trang.

### 8.2. Nhúng không làm dữ liệu hiện hành tự đồng bộ

Nếu nhúng `productNameCurrent` vào hàng nghìn đơn, khi Catalog đổi tên sản phẩm, hàng nghìn document có thể chứa tên cũ. Điều này có thể **đúng** nếu đó là tên tại thời điểm mua, nhưng **sai** nếu UI yêu cầu tên sản phẩm hiện hành.

Vì vậy, dù dùng document hay wide-column, trước khi copy một trường vẫn phải trả lời: **trường này là snapshot hay bản sao cần đồng bộ?**

## 9. Đồng bộ bản sao: “dual write” dễ sai ở đâu?

Giả sử API thay đổi Order:

~~~text
1. Ghi orders_by_id.status = READY_TO_SHIP
2. Ghi ready_orders_by_shop_day
3. Ghi orders_by_customer_month.status = READY_TO_SHIP
~~~

Nếu mọi thao tác nằm ngoài một transaction chung, service có thể chết giữa các bước:

~~~text
orders_by_id               = READY_TO_SHIP
ready_orders_by_shop_day   = chưa có O900
orders_by_customer_month   = PAID
~~~

Ba dữ liệu không nhất quán. Cách đảo thứ tự ghi cũng chỉ đổi loại trạng thái sai:

~~~text
1. Ghi bảng đọc READY thành công
2. Ghi source Orders thất bại

Kết quả: dashboard hiển thị đơn READY mà nguồn chưa xác nhận.
~~~

**Ghi tuần tự vào nhiều bảng không tự tạo atomicity đa bảng.** Một số NoSQL hỗ trợ giao dịch đa document/item trong phạm vi và giới hạn cụ thể; nếu sử dụng được, giao dịch có thể giảm một số rủi ro. Nhưng không được giả định mọi bảng, mọi partition hoặc dịch vụ thanh toán bên ngoài đều tham gia cùng transaction.

### 9.1. Có thể chấp nhận trễ, nhưng không chấp nhận mất đồng bộ vĩnh viễn

Với một dashboard, có thể chấp nhận:

~~~text
09:30:00  Source: READY_TO_SHIP
09:30:02  Read model: READY_TO_SHIP
~~~

Đây là **eventual consistency có mục tiêu độ trễ**. Điều không thể chấp nhận là 09:30:00 cập nhật source nhưng read model **vĩnh viễn không bao giờ được cập nhật** vì process chết và không có log/retry.

Để thiết kế vận hành được, cần một luồng thay đổi đủ bền và có thể phát lại.

## 10. Event, CDC và transactional outbox

Một cách phổ biến là cho nguồn dữ liệu chuẩn phát ra **sự kiện về các thay đổi đã được xác nhận**, sau đó các projector cập nhật các bảng đọc.

~~~mermaid
flowchart LR
    A["Lệnh: markReady(O900)"] --> B["Orders domain"]
    B --> C["Order source state"]
    C --> D["Committed change / Outbox / CDC"]
    D --> E["Message broker hoặc stream"]
    E --> F["Projector Q2"]
    E --> G["Projector Q3"]
    F --> H["orders_by_customer_month"]
    G --> I["ready_orders_by_shop_day"]
~~~

### 10.1. Một sự kiện thay đổi

~~~json
{
  "eventId": "order-O900-v4",
  "eventType": "OrderStatusChanged",
  "tenantId": "merchant-a",
  "orderId": "O900",
  "version": 4,
  "previousStatus": "PAID",
  "status": "READY_TO_SHIP",
  "shopId": "shop-12",
  "customerId": "U42",
  "createdAt": "2026-11-14T09:30:00Z",
  "totalVnd": 1000000,
  "occurredAt": "2026-11-14T09:34:00Z"
}
~~~

Các trường quan trọng:

| Trường | Lý do |
| --- | --- |
| `eventId` | Giúp phát hiện event được xử lý nhiều lần |
| `orderId` và `tenantId` | Định vị đúng đối tượng nghiệp vụ |
| `version` | Phân biệt thứ tự thay đổi của **cùng order** |
| `previousStatus`, `status` | Biết khi nào thêm/xóa bảng chỉ chứa READY |
| `createdAt`, `shopId` | Tính khóa projection theo thiết kế Q3 |
| `occurredAt` | Quan sát thời điểm phát sinh, không thay thế version khi phân xử cạnh tranh |

Event phải phản ánh một trạng thái nguồn **đã commit**, không phải mong muốn cập nhật chưa được xác nhận.

### 10.2. Transactional outbox khi có ranh giới transaction phù hợp

Nếu database hỗ trợ transaction bao gồm cả trạng thái Order và bản ghi outbox:

~~~text
BEGIN TRANSACTION
    UPDATE Order O900 (PAID -> READY_TO_SHIP, version 3 -> 4)
        IF currentVersion = 3 AND currentStatus = PAID
    INSERT Outbox(eventId = "order-O900-v4", payload)
COMMIT
~~~

Sau commit, worker outbox đọc sự kiện và gửi cho broker. Nếu worker gửi xong nhưng chết trước khi ghi checkpoint, nó có thể **gửi lại**. Vì vậy phía projector phải xử lý idempotent.

Điểm mạnh của outbox là tránh tình huống **Order đã commit nhưng sự kiện không bao giờ được ghi nhận** do process chết giữa thao tác database và gửi broker. Tuy nhiên, outbox phải được triển khai bằng **một giao dịch thực sự bao phủ hai ghi**; nếu chỉ gọi hai API write riêng, nó không giải quyết lỗi dual-write.

### 10.3. CDC/change stream

**Change Data Capture (CDC)** hoặc change stream phù hợp có thể lấy những thay đổi đã xảy ra ở source, chuyển chúng thành event rồi cập nhật các projection.

Cần biết:

- CDC có đầy đủ dữ kiện để dựng projection hay cần đọc thêm source?
- Có thứ tự thay đổi theo từng order không?
- Có giữ log đủ lâu để replay khi projector dừng nhiều giờ không?
- Có thể resume bằng checkpoint/token sau lỗi không?
- Có cơ chế nhận biết lỗ hổng, schema change và thao tác xóa không?

**Không phải mọi NoSQL đều có CDC/transactional outbox với cùng bảo đảm.** Thiết kế phải dựa trên khả năng thực tế của engine, phiên bản và cấu hình đang dùng.

## 11. Xử lý event lặp và đến sai thứ tự

Một pipeline thường ưu tiên **at-least-once delivery**, nghĩa là có thể nhận lại một sự kiện. Cũng có thể có nhiều worker và những thay đổi của cùng đối tượng được xử lý không đúng thứ tự nếu không tổ chức luồng phù hợp.

### 11.1. Sự kiện lặp

Giả sử `order-O900-v4` được broker giao hai lần. Nếu projector dùng thao tác ghi cùng khóa và cùng giá trị, bản chiếu có thể vẫn đúng. Nhưng nếu projector cộng `readyOrderCount += 1` ở mỗi lần nhận, event bị tính hai lần.

Do đó:

- Ghi projection với **khóa định danh ổn định**.
- Dùng `eventId` hoặc `(orderId, version)` để phát hiện xử lý lặp.
- Nếu cập nhật counter/aggregate, ghi dấu vết đã xử lý và tác động trong một giao dịch phù hợp; nếu không, phải có cơ chế reconcile.

### 11.2. Sự kiện sai thứ tự

Giả sử:

~~~text
v4: O900 -> READY_TO_SHIP
v5: O900 -> SHIPPED
~~~

Nhưng projector nhận v5 trước v4:

~~~text
t1: projector xử lý v5, xóa O900 khỏi bảng READY
t2: projector nhận v4 cũ, thêm O900 trở lại
~~~

Kết quả sai: đơn đã giao xuất hiện lại như đang chờ giao.

Một cách phòng vệ là giữ **phiên bản lớn nhất đã áp dụng**:

~~~text
ProjectionProgress[tenantId, orderId] = {
    lastAppliedVersion: 5,
    previousProjectionKey: ...,
    sourceState: SHIPPED
}
~~~

Khi nhận event v4, worker thấy `4 <= 5` nên bỏ qua. Khi nhận v6, xử lý theo version và cập nhật tiến độ.

**Lưu version ngay trong hàng READY là chưa đủ:** khi v5 xóa hàng, version ở hàng đó cũng biến mất. Nếu v4 đến muộn, không còn dấu vết nào trong bảng READY để ngăn nó tạo lại hàng. Cần một ledger/checkpoint hoặc một cơ chế tuần tự và ghi có điều kiện có hiệu lực ngay cả sau khi xóa.

### 11.3. Dấu vết version cũng phải được ghi an toàn

Giả sử worker làm:

~~~text
1. Ghi ProjectionProgress = v5
2. Xóa hàng READY
~~~

Nếu chết giữa bước 1 và 2, event v5 có thể bị xem là đã xử lý, nhưng hàng READY vẫn còn. Làm theo thứ tự ngược lại cũng có khoảng lỗi.

Vì vậy cần:

- Transaction phù hợp nếu cùng một storage hỗ trợ.
- Hoặc **quy trình idempotent có thể tiếp tục từ bước dang dở** với trạng thái tiến độ đủ chi tiết.
- Hoặc cơ chế projector đơn luồng theo khóa, đối soát source và replay có kiểm soát.

Chỉ một cột `lastAppliedVersion` **không tự làm nhiều mutation trên nhiều partition trở thành nguyên tử**.

### 11.4. Cẩn trọng với version và clock

`version` tăng đơn điệu nên được cập nhật bằng cơ chế kiểm soát cạnh tranh ở **nguồn chuẩn**, ví dụ compare-and-set/conditional update:

~~~text
UPDATE Order O900
IF version = 4
SET status = SHIPPED, version = 5
~~~

Đây là pseudocode; cú pháp phụ thuộc engine. Một timestamp từ điện thoại hoặc từ nhiều process có clock lệch **không phải thay thế an toàn** cho version nghiệp vụ khi cần quyết định event nào mới hơn.

## 12. Backfill: tạo bản đọc cho dữ liệu đã tồn tại

Một hệ thống đã có 5 triệu đơn mới được bổ sung Q3. Nếu chỉ projector theo dõi sự kiện **từ ngày triển khai**, các đơn READY từ hôm trước không xuất hiện trong bảng mới.

Cần **backfill** để dựng projection từ source:

~~~text
1. Tạo bảng read model mới.
2. Xác định mốc nhất quán / change-log checkpoint W.
3. Bắt đầu thu các thay đổi sau W theo cơ chế có thể replay.
4. Đọc source theo các phần nhỏ và tạo projection nền.
5. Replay thay đổi mới, áp dụng theo version phù hợp.
6. Đối soát với source.
7. Chỉ chuyển API sang bảng mới khi đã đạt yêu cầu.
~~~

### 12.1. Race condition giữa backfill và sự kiện mới

Ví dụ:

~~~text
10:00 Backfill đọc O900 v4 = READY_TO_SHIP
10:01 Orders xác nhận O900 v5 = SHIPPED
10:02 Projector xóa O900 khỏi bảng READY theo v5
10:03 Backfill ghi O900 READY từ ảnh chụp v4
~~~

Nếu không có điều kiện version, bảng mới **hồi sinh dữ liệu cũ**.

Cách phòng vệ có thể gồm:

- Dùng snapshot nhất quán tại mốc W và replay mọi thay đổi sau W đúng thứ tự.
- Đưa backfill và stream vào **một hàng đợi xử lý theo từng order** với thứ tự/version rõ.
- Dùng conditional update theo version tại nơi có thể bao phủ cả bản chiếu và dấu vết xóa.
- Đọc lại source trước khi ghi hoặc đối soát sau backfill, tùy SLA trễ cho phép.

Nếu database không hỗ trợ snapshot nhất quán và CDC có mốc replay phù hợp, phải thừa nhận khoảng hở và thiết kế cơ chế phát hiện/sửa lệch; không được tự giả định scan + replay luôn đúng.

### 12.2. Backfill có giới hạn tài nguyên

Nếu nguồn rất lớn:

- Chia đọc theo partition/token range hoặc cơ chế scan được engine hỗ trợ.
- Có checkpoint để tiếp tục sau lỗi, không bắt đầu lại toàn bộ.
- Giới hạn throughput để không làm chậm API đang hoạt động.
- Tránh quét lại những trường hoặc khoảng lịch sử không cần cho projection.
- Theo dõi progress, lỗi, lag, số bản ghi được sinh và sai lệch đối soát.

Nếu Q3 chỉ hiển thị 30 ngày gần nhất, có thể xem xét chỉ backfill phần dữ liệu phù hợp, nhưng phải xác định rõ điều kiện nghiệp vụ như “đơn tạo từ 30 ngày” hay “đơn còn ở READY bất kể ngày tạo”.

## 13. Khi nào phải đọc lại nguồn chuẩn?

Read model có thể trễ vài giây, nhưng một số thao tác **phải dựa vào trạng thái có thẩm quyền**.

Ví dụ một nhân viên bấm “Xác nhận đã giao” trên một hàng vừa xem ở bảng READY. Trong lúc đó, hệ thống khác đã hủy đơn hoặc thay đổi trạng thái.

Không nên:

~~~text
UI thấy READY trong projection
  -> API ghi SHIPPED ngay mà không kiểm tra
~~~

Nên:

~~~text
UI chọn Order O900
  -> API kiểm tra người gọi có quyền
  -> Orders thực hiện chuyển trạng thái có điều kiện
       IF currentStatus = READY_TO_SHIP
       AND version = expectedVersion
  -> nếu thành công: ghi nguồn chuẩn và phát thay đổi
  -> projection được cập nhật theo thay đổi đã xác nhận
~~~

Điều này kết hợp **đọc nhanh trên projection** với **ghi đúng qua nguồn chuẩn**.

### 13.1. Read-your-writes

Nếu khách vừa sửa một thông tin rồi mở màn hình danh sách và vẫn thấy giá trị cũ, trải nghiệm có thể khó hiểu. Những lựa chọn:

- Sau khi ghi thành công, trả về **đối tượng nguồn đã cập nhật** cho client hiển thị ngay.
- Tạm thời đọc source cho chính đối tượng vừa ghi.
- Chờ projection bắt kịp một version hoặc checkpoint trước khi trả kết quả.
- Dùng cơ chế optimistic UI có khả năng rollback và xử lý lỗi.

Không nên hứa “dữ liệu xuất hiện ngay ở mọi projection” nếu pipeline hiện tại chỉ có eventual consistency.

### 13.2. Bounded staleness

“Eventual consistency” tự nó không đảm bảo độ trễ **luôn dưới 3 giây**. Nếu muốn mục tiêu như `projectionLagP99 <= 3s`, hệ thống phải có metric, năng lực xử lý, giám sát backlog và quy tắc xử lý khi vượt ngưỡng.

Một dashboard có thể hiển thị cảnh báo “dữ liệu đang được đồng bộ” khi read model trễ. Một thao tác tài chính có thể bắt buộc kiểm tra trực tiếp từ nguồn trước khi quyết định.

## 14. Trường hợp nhiều nguồn chuẩn: tránh sở hữu chồng lấn

Một bảng đơn hàng có thể chứa:

~~~json
{
  "orderId": "O900",
  "paymentStatus": "PAID",
  "shippingStatus": "IN_TRANSIT"
}
~~~

Nếu Payments và Orders đều được phép **tự ghi `paymentStatus` như giá trị chuẩn**, hai dịch vụ có thể đưa ra quyết định xung đột. Cần phân định:

~~~text
Payments owns: payment transaction, capture/refund result
Orders owns:   order workflow, order fulfillment state
Shipping owns: shipment, tracking events

Orders.paymentStatus:
    chỉ là projection/tóm tắt từ Payments, không phải payment ledger
~~~

Tùy thiết kế domain, Orders có thể phản ánh một trạng thái “đã nhận tín hiệu thanh toán thành công”, nhưng không thay thế chứng cứ giao dịch tài chính của Payments.

### 14.1. Sở hữu dữ kiện theo câu hỏi, không chỉ theo tên trường

`status` là một tên quá rộng:

- `Order.status` là trạng thái xử lý đơn.
- `Payment.status` là trạng thái thanh toán.
- `Shipment.status` là trạng thái giao vận.
- `Projection.syncStatus` là trạng thái đồng bộ dữ liệu.

Chúng có thể liên quan nhưng **không được đồng nhất**. Ví dụ “đơn đã giao” không tự chứng minh tiền đã được capture thành công.

### 14.2. Quy trình sửa lệch phải biết tìm ai

Khi nhân viên thấy Orders nói “PAID” còn Payments chưa có giao dịch xác nhận:

1. Xác định nguồn nào có quyền quyết định sự kiện thanh toán.
2. Kiểm tra payment operation ID/ledger và trạng thái provider bằng quy trình đối soát.
3. Chỉnh projection/luồng nghiệp vụ theo sự thật đã xác nhận.
4. Không chỉ sửa thủ công trường `paymentStatus` ở bảng đơn cho “khớp màn hình”.

Mục tiêu là tìm **nguyên nhân và dữ kiện đúng**, không ép hai bản sao giống nhau bằng một phép ghi không có thẩm quyền.

## 15. Kiểm tra bất biến và đối soát dữ liệu lặp

Vì projection có thể trễ hoặc lỗi, cần cách **phát hiện và sửa sai khác** mà không phụ thuộc hoàn toàn vào người dùng báo lỗi.

### 15.1. Bất biến nghiệp vụ

Ví dụ:

~~~text
Nếu Order.status = READY_TO_SHIP ở source tại mốc T:
    expected read model có hàng READY tương ứng

Nếu Order.status != READY_TO_SHIP ở source tại mốc T:
    expected read model không có hàng READY tương ứng
~~~

Với `orders_by_customer_month`:

~~~text
Mỗi Order hợp lệ phải có đúng một hàng projection
trong partition customer/month tương ứng,
với status/total theo source version đã chọn.
~~~

Các bất biến này cần được đánh giá theo **mốc thời gian/version nhất quán**. Nếu nguồn vừa thay đổi trong 2 giây chờ projector, khác biệt tạm thời không nhất thiết là lỗi.

### 15.2. Đối soát không chỉ so số hàng

Giả sử bảng READY có 20 hàng, nhưng một hàng là đơn đã SHIPPED còn một đơn READY khác bị thiếu. **Số hàng vẫn bằng 20** nhưng dữ liệu sai.

Đối soát nên kiểm tra:

| Nhóm | Điều cần so |
| --- | --- |
| Khóa định danh | Đúng tenant/shop/orderId; không nhân bản |
| Tập kết quả | Có thiếu/hàng thừa không |
| Nội dung | Status, tổng tiền, customerId, version |
| Thứ tự | Có đúng `createdAt DESC, orderId ASC` không |
| Thời gian | Projection lag, age của dữ liệu |
| Quyền | Có lẫn dữ liệu khác tenant hoặc dữ liệu đã thu hồi quyền không |
| Xóa | Hàng đã xóa ở source có còn xuất hiện ở index/cache không |

### 15.3. Chiến lược tự sửa

Tùy hệ thống:

- **Replay event** từ checkpoint an toàn.
- **Rebuild một partition hoặc một tenant** từ source.
- **Reconcile theo orderId**, sửa hoặc xóa hàng projection sai.
- **Chạy full backfill có kiểm soát** khi đổi schema projection.
- **Tạm tắt đường đọc phụ** khi lag/error vượt giới hạn được phép.

Một projection có thể rebuild được là lợi thế vận hành lớn, nhưng điều này chỉ đúng nếu nguồn chuẩn và lịch sử thay đổi giữ **đầy đủ dữ liệu cần tái tạo**.

## 16. Thao tác xóa và vòng đời dữ liệu trong các bản sao

Đăng ký nhiều nơi lưu một dữ kiện có nghĩa khi cần xóa, đổi quyền hoặc hết hạn, phải xử lý **tất cả bản sao liên quan**.

Ví dụ một khách yêu cầu xóa dữ liệu hồ sơ theo chính sách phù hợp. Hệ thống cần biết:

- Hồ sơ chuẩn ở đâu?
- Cache và search index nào chứa dữ liệu đó?
- Projection danh sách đơn có chứa tên/địa chỉ không?
- Snapshot giao dịch nào phải giữ hoặc xóa theo căn cứ và chính sách lưu trữ tương ứng?
- Event/log/backup có chứa trường nhạy cảm không, và có cơ chế retention nào?

Không được mặc định “xóa Customer document” sẽ tự xóa mọi projection, cache hoặc bản sao do service khác quản lý.

### 16.1. Dấu xóa và replay

Giả sử một tài liệu bị xóa khỏi nguồn chuẩn ở version 6. Nếu projector xóa index rồi nhận lại sự kiện **version 5** “document updated”, nó có thể tạo lại tài liệu đã xóa nếu không ghi dấu phiên bản hoặc quy tắc xử lý tương ứng.

**Deletion tombstone/ledger version** ở pipeline đồng bộ giúp ngăn việc phục hồi trái ý muốn từ event cũ. Phải xác định thời gian giữ dấu vết đủ bao phủ cửa sổ replay và chính sách vòng đời.

### 16.2. Dữ liệu nhạy cảm trong projection

Một read model chỉ cần hiển thị:

~~~text
orderId, createdAt, status, totalVnd
~~~

thường không nên sao chép thêm:

~~~text
passportNumber, fullPaymentCard, secretToken, privateNotes
~~~

Chỉ vì có thể “lưu cùng cho tiện” không phải lý do hợp lệ. Mỗi bản sao tăng diện tích cần kiểm soát quyền, mã hóa, giám sát và xóa dữ liệu.

## 17. Chi phí của việc lặp dữ liệu

Lặp dữ liệu thường giảm chi phí đọc cho một đường truy cập nhưng tăng chi phí ghi và vận hành.

Một mô hình sơ bộ:

\[
C_{\text{total}}
= C_{\text{source storage}}
+ C_{\text{projection storage}}
+ C_{\text{extra writes}}
+ C_{\text{sync and rebuild}}
+ C_{\text{reads}}
+ C_{\text{operations}}
\]

Trong đó:

- `extra writes` gồm thêm/sửa/xóa ở các projection và index.
- `sync and rebuild` gồm broker/CDC, backfill, đối soát, retry.
- `reads` có thể **giảm** nhờ index/read model mới.
- `operations` gồm theo dõi lag, sửa sai khác, backup, triển khai schema.

### 17.1. Ví dụ dung lượng minh họa

Giả sử hệ thống có **1 triệu đơn**:

~~~text
Source order summary trung bình:         1.500 byte/đơn
Projection theo khách hàng:                280 byte/đơn
Projection theo cửa hàng:                  320 byte/đơn

Phần dữ liệu lặp trung bình nếu mỗi đơn có 2 projection:
  1.000.000 × (280 + 320) byte
  = 600.000.000 byte
  = 0,6 GB (thập phân)

Nếu có 3 bản sao đầy đủ:
  0,6 GB × 3 = 1,8 GB (chỉ phần dữ liệu logic lặp)
~~~

Số này **không phải dung lượng thực đo**. Chưa tính chỉ mục, metadata, record versions, tombstones, nén, compaction, replication đặc thù, cache, snapshot hoặc dữ liệu tạm khi rebuild. Bảng `READY_TO_SHIP` còn có thể chỉ chứa một phần đơn; ví dụ “mỗi đơn có hai projection” là giả định có chủ đích để tính dung lượng.

### 17.2. Write amplification

Một thay đổi trạng thái Order có thể dẫn tới:

~~~text
1 ghi ở nguồn Orders
+ 1 event/outbox record
+ 1 cập nhật orders_by_customer_month
+ 1 thêm hoặc xóa ready_orders_by_shop_day
+ cập nhật cache/index liên quan
~~~

Vì vậy **số ghi vật lý trên mỗi thao tác nghiệp vụ có thể tăng** theo số read model. Không nhất thiết tất cả thao tác đều cập nhật mọi projection; ví dụ đổi ghi chú nội bộ không liên quan Q2/Q3 thì không cần ghi lại hai bảng đó.

Thiết kế projector theo **sự thay đổi thực sự của những trường được chiếu** sẽ giảm ghi thừa.

### 17.3. Một read model “nhiều mục đích” cũng có đánh đổi

Nếu cố gộp mọi màn hình vào một bảng với rất nhiều trường và index:

- Dung lượng mỗi hàng tăng.
- Một trường đổi kéo theo nhiều cập nhật.
- Đường đọc có thể không dùng được thứ tự phù hợp cho mọi query.
- Việc triển khai quyền/retention cho từng trường phức tạp hơn.

Ngược lại, tạo một bảng cho **mọi biến thể** bộ lọc/sort cũng gây bùng nổ số cấu trúc. Hãy nhóm các truy vấn thành **query families** và lựa chọn những đường đọc có tần suất/giá trị đủ lớn.

## 18. Kiểm soát đồng thời ở nguồn chuẩn

Read model không nên trở thành nơi thực thi lệnh “trừ kho”, “chốt tiền” hoặc “chuyển trạng thái” chỉ vì nó chứa bản sao trường liên quan.

Giả sử hai worker cùng muốn:

~~~text
Worker A: O900 -> SHIPPED
Worker B: O900 -> CANCELLED
~~~

Nếu cả hai chỉ đọc một projection cũ đang READY và ghi tùy ý, có thể tạo hai kết quả xung đột. Nguồn Orders cần một **state machine** cùng cơ chế cập nhật có điều kiện:

~~~text
UPDATE Orders[O900]
SET status = SHIPPED, version = 5
IF status = READY_TO_SHIP AND version = 4
~~~

Đây là pseudocode, không phải cú pháp chung của mọi engine. Một worker được chấp nhận theo điều kiện; worker còn lại phải đọc lại trạng thái nguồn, phân loại xung đột rồi xử lý theo nghiệp vụ. Sau khi nguồn xác nhận, các projection nhận thay đổi qua event/CDC.

### 18.1. Idempotency khác với consistency

Nếu một yêu cầu chuyển trạng thái bị timeout rồi retry, phải xác định:

1. Request cũ đã được thực hiện chưa?
2. Source hiện ở trạng thái/version nào?
3. Việc gửi lại có tạo thêm tác động phụ như thu tiền/gửi hàng không?

**Idempotency key** hoặc định danh thao tác ổn định giúp chống thực hiện lặp cùng ý định. **Version/conditional update** giúp chống hai ý định khác nhau ghi đè nhau. **Projection sync** giúp bản đọc phản ánh trạng thái nguồn. Cả ba giải quyết các vấn đề khác nhau.

### 18.2. Sự kiện có thể lặp, nhưng tổng hợp không được cộng sai

Nếu projection là số đơn READY theo shop:

~~~text
readyCount(shop-12) = 12
~~~

Projector nhận lại cùng sự kiện “O900 chuyển READY” hai lần rồi tăng hai lần sẽ thành 14 thay vì 13. Với aggregate, cần:

- Dấu vết event đã áp dụng và điều kiện nguyên tử tương ứng.
- Hoặc cập nhật dựa trên trạng thái trước/sau được kiểm soát.
- Hoặc tính lại từ nguồn/read model định kỳ để sửa lệch.

**Cập nhật dạng SET theo khóa định danh có thể dễ idempotent hơn INCREMENT**, nhưng cũng phải xét event đến sai thứ tự và xóa.

## 19. Thực hành: xây read model và quan sát lệch dữ liệu

Một bài lab không cần cluster lớn để học nguyên tắc. Có thể dùng bộ dữ liệu mô phỏng:

~~~text
Order source:
O100 -> U42, shop-12, READY_TO_SHIP, version 3, createdAt 09:00
O101 -> U42, shop-12, PAID,          version 2, createdAt 09:10
O102 -> U51, shop-12, READY_TO_SHIP, version 5, createdAt 09:20
O103 -> U51, shop-13, SHIPPED,       version 6, createdAt 09:30
~~~

Xây hai cấu trúc:

~~~text
byCustomer[(tenantId, customerId)] -> danh sách OrderSummary
readyByShop[(tenantId, shopId)]    -> danh sách OrderSummary đang READY
~~~

### 19.1. Bước 1 — Dựng projection từ nguồn

Pseudocode:

~~~python
from collections import defaultdict

orders = [
    {"id": "O100", "tenant": "merchant-a", "customer": "U42",
     "shop": "shop-12", "status": "READY_TO_SHIP",
     "version": 3, "createdAt": "09:00"},
    {"id": "O101", "tenant": "merchant-a", "customer": "U42",
     "shop": "shop-12", "status": "PAID",
     "version": 2, "createdAt": "09:10"},
    {"id": "O102", "tenant": "merchant-a", "customer": "U51",
     "shop": "shop-12", "status": "READY_TO_SHIP",
     "version": 5, "createdAt": "09:20"},
    {"id": "O103", "tenant": "merchant-a", "customer": "U51",
     "shop": "shop-13", "status": "SHIPPED",
     "version": 6, "createdAt": "09:30"},
]

by_customer = defaultdict(list)
ready_by_shop = defaultdict(list)

for order in orders:
    by_customer[(order["tenant"], order["customer"])].append(order)
    if order["status"] == "READY_TO_SHIP":
        ready_by_shop[(order["tenant"], order["shop"])].append(order)

for items in by_customer.values():
    items.sort(key=lambda item: (item["createdAt"], item["id"]),
               reverse=True)

print([o["id"] for o in by_customer[("merchant-a", "U42")]])
print([o["id"] for o in ready_by_shop[("merchant-a", "shop-12")]])
~~~

Kết quả kỳ vọng:

~~~text
['O101', 'O100']
['O100', 'O102']
~~~

Trong ví dụ nhỏ này, các danh sách Python đại diện cho read model. Trong hệ thật, read model cần **khóa duy nhất và phân trang**, không dùng danh sách trong bộ nhớ cho dữ liệu lớn.

### 19.2. Bước 2 — Làm source thay đổi mà chưa cập nhật projection

Giả sử O100 được xác nhận SHIPPED ở source version 4. Nếu chỉ sửa:

~~~text
source[O100].status = SHIPPED
source[O100].version = 4
~~~

mà không thay đổi `readyByShop`, danh sách READY **vẫn chứa O100**. Đây là hành vi sai có chủ đích của bài lab, minh họa tại sao read model phải được đồng bộ.

Nếu dùng cùng đối tượng Python mutable trong cả source lẫn projection, thao tác sửa có thể vô tình làm thay đổi dữ liệu được tham chiếu ở nhiều nơi. Để mô phỏng **bản sao tách biệt**, cần dùng `dict(order)` hoặc cơ chế copy tương đương khi tạo projection. Trong hệ thực, các bản ghi ở hai bảng/document khác nhau thường không tự chia sẻ tham chiếu bộ nhớ.

### 19.3. Bước 3 — Xử lý event v4

~~~json
{
  "eventId": "O100-v4",
  "orderId": "O100",
  "version": 4,
  "previousStatus": "READY_TO_SHIP",
  "status": "SHIPPED"
}
~~~

Áp dụng logic:

~~~text
Nếu version mới hơn version đã áp dụng:
    cập nhật status ở projection theo khách
    loại O100 khỏi readyByShop(shop-12)
    ghi nhận version đã áp dụng = 4
~~~

Sau đó bảng READY chỉ còn **O102** ở shop-12.

### 19.4. Bước 4 — Phát lại event cũ

Cho projector nhận thêm:

~~~json
{
  "eventId": "O100-v3",
  "orderId": "O100",
  "version": 3,
  "status": "READY_TO_SHIP"
}
~~~

Nếu worker chỉ “nhìn status là READY thì thêm”, O100 sẽ xuất hiện lại. Hãy thiết kế ledger/checkpoint để **v3 không ghi đè v4** và lý giải ranh giới nguyên tử của thao tác xóa + ghi version.

### 19.5. Bước 5 — Thử rebuild từ source

Xóa toàn bộ read model mô phỏng rồi dựng lại bằng **snapshot source mới nhất**. Kiểm tra rằng mọi trạng thái ở projection tương ứng với nguồn được chọn. Trong production, rebuild cũng phải giải quyết các thay đổi phát sinh trong lúc quá trình đang chạy, thông qua mốc dữ liệu và cơ chế replay phù hợp.

## 20. Các chỉ số nên theo dõi

Một bản sao phục vụ đọc cần được vận hành như **một thành phần hệ thống**, không phải tập dữ liệu phát sinh rồi bỏ mặc.

| Chỉ số | Câu hỏi vận hành |
| --- | --- |
| `projection_lag_seconds` | Một thay đổi mất bao lâu để xuất hiện ở read model? |
| `projector_errors_total` | Có event nào không thể áp dụng? |
| `event_replay_total` | Lượng event được xử lý lại nhiều hay ít? |
| `out_of_order_events_total` | Có nhiều event đến sai thứ tự không? |
| `missing_projection_rows` | Nguồn có dữ kiện nhưng bảng phụ thiếu bao nhiêu? |
| `stale_projection_rows` | Bảng phụ còn giữ dữ kiện đã đổi/xóa bao nhiêu? |
| `duplicate_projection_keys` | Có hàng trùng định danh hoặc kết quả merge trùng không? |
| `read_model_p95_latency` | Đường truy cập mới có đáp ứng SLA? |
| `extra_write_qps` | Lặp dữ liệu tăng bao nhiêu write? |
| `projection_storage_bytes` | Bản sao/index tốn bao nhiêu dung lượng? |
| `backfill_checkpoint_age` | Backfill/rebuild có đang kẹt? |
| `authorization_failures` | Có query sai phạm vi tenant/quyền hay không? |

Đặt cảnh báo cần xét **tính chất nghiệp vụ**. Một danh sách gợi ý sản phẩm có thể chịu độ trễ đồng bộ lớn hơn màn hình điều phối giao hàng; một hoạt động thanh toán có thể cần kiểm tra nguồn có thẩm quyền ngay tại thời điểm thực thi.

## 21. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách khắc phục |
| --- | --- | --- |
| “Mỗi dữ kiện phải chỉ tồn tại ở một nơi.” | Buộc các đường đọc khó hoặc quá nhiều join/quét | Cho phép bản chiếu có mục đích và chủ sở hữu |
| “Bản copy nào mới nhất theo timestamp là đúng.” | Clock lệch, retry và event sai thứ tự | Dùng source authority và version/quy tắc nghiệp vụ |
| Đồng bộ giá Catalog vào mọi đơn cũ | Thay đổi điều khoản giao dịch đã chốt | Tách `currentPrice` và `priceAtPurchase` |
| Dùng cache làm nguồn duy nhất cho Order | Eviction/TTL làm mất trạng thái nghiệp vụ | Để cache có thể nạp lại từ source |
| Ghi hai bảng tuần tự rồi coi là atomic | Crash giữa hai ghi tạo dữ liệu lệch | Giao dịch phù hợp hoặc pipeline có replay/reconcile |
| Projector xử lý mỗi event không kiểm tra version | Event đến muộn hồi sinh trạng thái cũ | Chống lặp và xử lý version theo entity |
| Xóa hàng projection mà mất luôn watermark | Event cũ có thể thêm lại hàng đã xóa | Ledger/tombstone version đủ bền hoặc đồng bộ tuần tự |
| Backfill từ ảnh chụp cũ đè event mới | Lệch dữ liệu ngay khi triển khai | Mốc replay, version gating và reconciliation |
| Sao chép mọi trường vào mọi read model | Tăng chi phí, rủi ro quyền và dữ liệu nhạy cảm | Projection tối thiểu theo query |
| Dùng projection trễ để ra quyết định ghi quan trọng | Thao tác trên trạng thái không còn đúng | Ghi qua source với điều kiện/version |
| Chỉ đối soát số hàng | Thiếu/thừa có thể triệt tiêu nhau | So theo ID, version, status và thời điểm |
| Xóa hồ sơ gốc mà quên search/cache | Vẫn lộ dữ liệu đã yêu cầu xử lý | Quản lý vòng đời trên mọi bản sao theo chính sách |

## 22. Bài tập thiết kế

### Bài 1 — Phân loại trường dữ liệu

Một đơn hàng lưu:

~~~text
productName
currentProductPrice
unitPriceAtPurchase
customerDisplayName
deliveryAddressAtCheckout
paymentStatus
shipmentTrackingNumber
~~~

Hãy chỉ ra trường nào nên được xem là **dữ kiện hiện hành từ một domain khác**, trường nào là **snapshot đã chốt**, trường nào chỉ là **projection để hiển thị**. Với mỗi trường, nêu chủ sở hữu và quy tắc cập nhật khi nguồn thay đổi.

### Bài 2 — Thiết kế read model mới

Ứng dụng bổ sung truy vấn:

> “Xem 50 đơn `CANCELLED` mới nhất của shop-12, sắp theo thời điểm hủy.”

Hãy thiết kế partition key, clustering columns và bucket phù hợp cho một hệ wide-column. Giải thích vì sao `cancelledAt` có thể quan trọng hơn `createdAt`; khi nào cần bảng riêng, khi nào một secondary index đủ dùng.

### Bài 3 — Xử lý event sai thứ tự

Projector nhận:

~~~text
O900-v7 -> DELIVERED
O900-v5 -> READY_TO_SHIP
O900-v6 -> SHIPPED
~~~

Hãy thiết kế:

1. Dấu vết version cho mỗi Order.
2. Cách xóa khỏi các bảng chỉ chứa trạng thái tương ứng.
3. Cách ngăn v5 tạo lại hàng READY sau v7.
4. Điều gì xảy ra nếu worker chết giữa cập nhật projection và watermark?

### Bài 4 — Tính chi phí lặp dữ liệu

Một hệ có 3 triệu đơn, mỗi đơn có 1,2 KB dữ liệu chuẩn; thêm hai projection lần lượt 300 B và 500 B/đơn, với replication factor 3.

Hãy tính phần dung lượng **logic** thêm và phần dữ liệu lặp sau nhân bản, rồi nêu những overhead chưa tính. Nếu một projection chỉ chứa 10% đơn còn hiệu lực, phép ước tính cần điều chỉnh ra sao?

### Bài 5 — Backfill không mất event mới

Giả sử projector đang cập nhật read model liên tục trong khi backfill cần quét 50 triệu đơn. Hãy mô tả mốc change log, checkpoint, version gating, giới hạn throughput và quy trình so sánh dữ liệu trước khi chuyển API sang read model mới.

### Bài 6 — Sở hữu dữ liệu giữa các service

Orders hiển thị `paymentStatus=PAID` nhưng Payments trả về `CAPTURE_PENDING`. Hãy xác định:

- Service nào có quyền quyết định điều gì?
- Hệ thống cần truy vấn lịch sử giao dịch nào?
- Khi nào được phép sửa projection của Orders?
- Vì sao không nên tùy tiện ghi `PAID` ở cả hai nơi cho giống nhau?

## Kết luận

**Lặp dữ liệu phục vụ đọc** là một kỹ thuật thiết kế có chủ đích trong NoSQL: dùng thêm index, document nhúng, bảng theo truy vấn, projection hoặc cache để các màn hình có thể trả kết quả nhanh theo những khóa và thứ tự mà ứng dụng thật sự cần.

Để lặp dữ liệu an toàn, phải đồng thời xác định:

- **Nguồn có thẩm quyền cho từng dữ kiện:** Catalog sở hữu giá hiện hành, Orders sở hữu giá đã chốt và luồng xử lý đơn, Payments sở hữu lịch sử giao dịch thanh toán.
- **Ý nghĩa của từng bản sao:** snapshot lịch sử không đồng nghĩa cache cần cập nhật; projection phục vụ đọc không có quyền quyết định nghiệp vụ.
- **Đường đồng bộ đáng tin cậy:** event/CDC/outbox phù hợp, retry, checkpoint, version và xử lý dữ liệu sai thứ tự.
- **Khả năng tái tạo và đối soát:** backfill, replay, sửa lệch và quản lý xóa trên mọi bản sao liên quan.
- **Chi phí và yêu cầu vận hành:** tăng write/storage để giảm read, nhưng cần đo latency, projection lag, tính đúng đắn và bảo mật.

Thiết kế tốt không cố làm mọi bản copy giống nhau bằng mọi giá. Nó bảo đảm **mỗi giá trị có đúng ý nghĩa và chủ sở hữu**, còn những cấu trúc được lặp để đọc **phản ánh nguồn phù hợp trong mức nhất quán đã cam kết**, có thể được kiểm chứng và phục hồi khi có lỗi.
