# Mô hình khóa–giá trị và lựa chọn đơn vị dữ liệu được truy cập nguyên khối

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích mô hình **khóa–giá trị (key–value)**, cách ứng dụng tìm dữ liệu bằng khóa và những giới hạn khi cần truy vấn theo thuộc tính hoặc quan hệ.
- Chuyển yêu cầu nghiệp vụ thành **mẫu truy cập** để quyết định dữ liệu nào nên nằm chung trong một giá trị, dữ liệu nào nên tách thành các khóa khác nhau.
- Thiết kế khóa, cấu trúc giá trị, vòng đời và quy tắc cập nhật cho một trường hợp thực tế; nhận diện vấn đề khi có cập nhật đồng thời.
- Đánh giá đánh đổi về kích thước giá trị, số lượt đọc/ghi, tính nhất quán, khóa nóng và khả năng mở rộng.
- Biết khi nào nên dùng mô hình khóa–giá trị và khi nào mô hình quan hệ, document hoặc cột rộng phù hợp hơn.

Trong **DATABASE_DATA_MODELING**, mục tiêu là rèn kỹ năng đi từ yêu cầu nghiệp vụ đến thực thể, quan hệ, ràng buộc và lược đồ vật lý có thể kiểm chứng. Mô hình khóa–giá trị cho thấy một lựa chọn rất khác so với việc bắt đầu bằng các bảng và phép nối: trước hết, ta hỏi **ứng dụng biết khóa nào và cần lấy phần dữ liệu nào cùng lúc?**

## 1. Bản chất của mô hình khóa–giá trị

Ở mức khái niệm, một kho khóa–giá trị ánh xạ một **khóa duy nhất trong phạm vi kho** tới một **giá trị**:

```text
key -> value

cart:shop_17:user_42 -> {"items":[{"sku":"A17","qty":2}]}
session:s_89          -> {"userId":"u_42","role":"buyer"}
feature:checkout:v2  -> {"enabled":true}
```

Thao tác cơ bản thường có dạng:

| Thao tác | Ý nghĩa |
| --- | --- |
| `get(key)` | Tìm giá trị tương ứng với một khóa đã biết. |
| `put(key, value)` | Tạo mới hoặc cập nhật giá trị gắn với khóa. |
| `delete(key)` | Xóa ánh xạ khóa–giá trị. |
| `get nhiều key` hoặc thao tác điều kiện | Có thể được hệ quản trị cung cấp; cú pháp, bảo đảm và giới hạn khác nhau theo sản phẩm. |

**Khóa** thường là chuỗi hoặc một định danh có thể mã hóa ổn định. **Giá trị** có thể là văn bản, byte, JSON đã tuần tự hóa, hoặc một kiểu dữ liệu mà hệ quản trị hỗ trợ. Cơ sở dữ liệu khóa–giá trị cơ bản không nhất thiết hiểu các thuộc tính bên trong giá trị: ứng dụng chịu trách nhiệm diễn giải chúng.

Ví dụ, nếu chỉ biết `GET cart:shop_17:user_42`, ta lấy được giỏ hàng của người dùng đó nhanh và trực tiếp. Nhưng câu hỏi “có bao nhiêu giỏ hàng chứa SKU A17?” **không tự động có lời giải hiệu quả** bằng cùng thiết kế: truy vấn này không có sẵn khóa của các giỏ hàng cần tìm.

Một số hệ thống thương mại cung cấp thêm chỉ mục phụ, kiểu dữ liệu có cấu trúc, truy vấn hay giao dịch. Đây là **khả năng cụ thể của hệ quản trị**, không phải tính chất bắt buộc của mọi mô hình khóa–giá trị.

> **Phân biệt:** “Đọc một giá trị theo một khóa” mô tả **đơn vị truy cập logic**. “Cập nhật nguyên tử” mô tả **bảo đảm giao dịch**. Đọc trọn giá trị không tự nó chứng minh một chuỗi đọc–sửa–ghi là an toàn khi nhiều người cùng cập nhật.

## 2. Bắt đầu từ mẫu truy cập, không bắt đầu từ cấu trúc bảng

Giả sử hệ thống bán hàng cần quản lý giỏ hàng. Trước khi đặt tên key hoặc chọn Redis, DynamoDB hay hệ thống khác, hãy liệt kê hành vi nghiệp vụ.

| Nghiệp vụ | Dữ liệu đầu vào đã biết | Dữ liệu cần lấy hoặc đổi | Tần suất / yêu cầu |
| --- | --- | --- | --- |
| Mở giỏ hàng | Shop ID và user ID | Toàn bộ danh sách mặt hàng, số lượng | Thường xuyên; đọc nhanh |
| Thêm hoặc đổi số lượng | Shop ID, user ID, SKU | Một mục trong giỏ; trả về trạng thái mới | Thường xuyên; tránh ghi đè mất cập nhật |
| Xóa giỏ hết hạn | Khóa giỏ hoặc chính sách hết hạn | Cả giỏ hàng | Theo vòng đời; có thể tự hết hạn |
| Xác nhận thanh toán | Shop ID và user ID | Giỏ tại một thời điểm và giá/tồn kho hiện hành | Phải kiểm tra lại các nguồn dữ liệu có thẩm quyền |
| Báo cáo SKU phổ biến | Khoảng thời gian, SKU | Nhiều giỏ hoặc các sự kiện giao dịch | Truy vấn tổng hợp; cần mô hình đọc riêng |

Ba hàng đầu gợi ý việc truy cập giỏ theo một khóa ổn định. Hai hàng sau cho thấy **không nên bắt một giá trị giỏ hàng giải quyết mọi bài toán**, đặc biệt là giao dịch mua hàng và phân tích.

Một cách lập luận hữu ích:

1. **Ai biết khóa?** Màn hình giỏ hàng biết shop ID và user ID; báo cáo toàn hệ thống thường không biết khóa của từng giỏ.
2. **Đọc cùng nhau đến đâu?** Nếu mỗi lần mở trang phải lấy mọi mục trong giỏ, gộp chúng có thể giảm số lượt truy cập.
3. **Ghi cùng nhau đến đâu?** Nếu nhiều thiết bị sửa cùng giỏ, cần kiểm soát tranh chấp; nếu các phần được sửa độc lập với tần suất cao, gộp có thể gây nghẽn.
4. **Sống và hết hạn cùng nhau không?** Các mục trong một giỏ có thể có chung TTL; đơn hàng đã thanh toán thì cần vòng đời và tính bền vững riêng.
5. **Có ràng buộc hoặc truy vấn vượt ra ngoài giá trị không?** Ví dụ giữ duy nhất email trên nhiều người dùng, thống kê tổng tiền theo tháng, hoặc nối sản phẩm với nhà cung cấp.

Đó là quá trình xác định **đơn vị dữ liệu được truy cập nguyên khối**: một nhóm thông tin mà phần lớn thao tác nghiệp vụ cần lấy, ghi, hoặc quản lý vòng đời như một đơn vị. Khái niệm này gần với *aggregate* trong thiết kế hướng miền, nhưng không đồng nghĩa với mọi aggregate đều phải lưu bằng một key.

## 3. Ví dụ thiết kế: một giỏ hàng trên một khóa

Giả định nghiệp vụ của ví dụ:

- Mỗi người dùng có tối đa một giỏ đang hoạt động trong một shop.
- Giao diện thường tải toàn bộ giỏ; giỏ thường nhỏ, nhưng cần đặt giới hạn kích thước.
- Giỏ chưa thanh toán có thể hết hạn sau 30 ngày kể từ lần cập nhật cuối.
- Một người dùng có thể mở nhiều tab hoặc thiết bị và cùng sửa giỏ.
- Giá bán, khuyến mãi và tồn kho được xác thực lại khi đặt hàng; giỏ chỉ lưu tham chiếu và số lượng cần mua.

### 3.1. Chọn khóa

```text
cart:<shopId>:<userId>
cart:shop_17:user_42
```

Cấu trúc khóa trên vừa phân biệt miền dữ liệu `cart`, vừa bảo đảm hai shop có thể có giỏ riêng cho cùng người dùng. Khi thiết kế khóa, cần làm rõ:

- **Tính duy nhất:** một cặp `(shopId, userId)` ánh xạ tới một giỏ đang hoạt động; nếu nghiệp vụ cho nhiều giỏ, bổ sung `cartId` hoặc thay đổi ánh xạ.
- **Tính ổn định:** tránh dùng email, số điện thoại hoặc tên có thể đổi làm định danh chính.
- **Khả năng phân tách:** nếu ID có thể chứa dấu phân cách `:`, hãy dùng quy tắc mã hóa hoặc định dạng khóa không nhập nhằng.
- **Riêng tư:** khóa có thể xuất hiện trong log, metrics, backup; ưu tiên ID nội bộ thay cho dữ liệu nhạy cảm.
- **Phân vùng:** khóa ảnh hưởng việc phân phối tải; nếu hệ quản trị dùng hàm băm, một khóa cực kỳ phổ biến có thể tạo *hot key*.

Không tồn tại cú pháp khóa chuẩn cho mọi sản phẩm. Dấu hai chấm ở đây là quy ước dễ đọc, không phải quy định của mô hình.

### 3.2. Chọn giá trị

```json
{
  "schemaVersion": 1,
  "cartId": "c_908",
  "revision": 8,
  "items": [
    { "sku": "A17", "quantity": 2 },
    { "sku": "B03", "quantity": 1 }
  ],
  "updatedAt": "2026-11-22T01:30:00Z"
}
```

Giải thích các trường:

| Trường | Vai trò |
| --- | --- |
| `schemaVersion` | Cho phép ứng dụng đọc và chuyển đổi giá trị theo phiên bản cấu trúc. |
| `cartId` | ID nghiệp vụ của giỏ, hữu ích cho logging hoặc kết nối với quy trình đặt hàng. |
| `revision` | Số phiên bản logic hỗ trợ so sánh khi cập nhật; **chỉ có tác dụng bảo vệ** nếu hệ lưu trữ cung cấp thao tác ghi có điều kiện hoặc giao dịch phù hợp. |
| `items` | Những mục thường được đọc cùng nhau; mỗi SKU xuất hiện nhiều nhất một lần. |
| `updatedAt` | Thời điểm cập nhật phục vụ nghiệp vụ hoặc quan sát; không thay thế cơ chế TTL của kho lưu trữ. |

**TTL (time to live)** nên được quản lý bằng khả năng hết hạn của hệ lưu trữ nếu có, thay vì tin rằng trường `updatedAt` sẽ tự xóa dữ liệu. Việc gia hạn TTL mỗi lần thao tác hay chỉ khi có cập nhật là một **quy tắc nghiệp vụ** phải xác định rõ. Cơ chế xóa vật lý có thể không diễn ra đúng từng mili giây tại thời điểm hết hạn.

### 3.3. Đọc và cập nhật

Đọc giỏ là một lần tra cứu khóa:

```text
key = "cart:shop_17:user_42"
cart = store.get(key)
if cart is absent:
    cart = empty_cart()
return cart
```

Khi thêm SKU, ứng dụng có thể thực hiện thao tác đọc–sửa–ghi. Nhưng nếu hai thiết bị đọc cùng `revision = 8`, thiết bị A thêm SKU C01 còn thiết bị B đổi số lượng A17, thì việc cả hai ghi đè toàn bộ giá trị có thể làm mất một trong hai thay đổi.

Do đó, cần **ghi có điều kiện theo phiên bản** hoặc dùng thao tác nguyên tử mà hệ quản trị hỗ trợ. Mã dưới đây là **giả mã độc lập với sản phẩm**, không phải lệnh của một hệ cơ sở dữ liệu cụ thể:

```text
function setQuantity(shopId, userId, sku, quantity):
    key = cartKey(shopId, userId)

    repeat with bounded retries:
        current, storageVersion = store.getWithVersion(key)
        next = changeQuantity(current or emptyCart(), sku, quantity)
        validate(next)

        ok = store.putIfVersionMatches(
            key,
            expectedVersion = storageVersion,
            value = next,
            ttl = 30 days
        )
        if ok:
            return next

    raise ConcurrentUpdateError
```

Điểm cần hiểu: vòng lặp chỉ an toàn nếu **kiểm tra phiên bản và ghi** là một thao tác có tính nguyên tử theo bảo đảm của kho dữ liệu. Việc tăng `revision` trong JSON rồi gọi `put` thông thường **không đủ**. Hệ thống không hỗ trợ so sánh–đổi (*compare-and-swap*, CAS) sẽ cần cơ chế phù hợp khác, như thao tác cập nhật nguyên tử, script/giao dịch theo khả năng của sản phẩm, hoặc thay đổi mô hình dữ liệu.

Với API thực tế, cũng nên đặt giới hạn số lần thử lại, xử lý request lặp bằng idempotency key khi cần và thông báo xung đột rõ ràng. Không thực hiện vòng lặp vô hạn khi một khóa liên tục bị cập nhật.

## 4. Quyết định ranh giới giá trị: gộp hay tách?

Không có công thức “cứ thuộc cùng một thực thể thì để cùng một giá trị”. Hãy so sánh các phương án trên **chính những thao tác nghiệp vụ phải hỗ trợ**.

| Phương án | Cách lưu minh họa | Ưu điểm | Chi phí / rủi ro |
| --- | --- | --- | --- |
| **Cả giỏ một giá trị** | `cart:shop_17:user_42 → {items:[...]}` | Đọc toàn giỏ một lần, hết hạn cùng nhau, dễ dựng giao diện | Sửa một mục có thể phải ghi cả giỏ; cạnh tranh cập nhật; giá trị lớn dần |
| **Một mục một khóa** | `cart-item:c_908:A17 → {quantity:2}` | Đổi từng mục độc lập, giá trị nhỏ | Cần biết/dò danh sách SKU; tải giỏ cần nhiều key; xóa trọn giỏ và đồng bộ các mục phức tạp |
| **Giỏ + các mục tách riêng** | `cart:c_908 → {itemIds:[...]}` và nhiều khóa item | Linh hoạt khi từng mục lớn hoặc thay đổi riêng | Phát sinh rủi ro danh sách và mục không khớp; thường cần giao dịch hoặc cơ chế sửa lỗi |
| **Kho dữ liệu có cấu trúc phù hợp** | Document với cập nhật trường; hoặc bảng quan hệ `Cart`/`CartItem` | Có thể cập nhật phần tử, đánh chỉ mục hoặc ràng buộc theo năng lực hệ thống | Chi phí mô hình và thao tác phụ thuộc hệ quản trị |

Trong ví dụ này, **một khóa cho một giỏ** là điểm xuất phát hợp lý vì yêu cầu đọc toàn giỏ nổi trội, các mục có vòng đời giống nhau và kích thước được giới hạn. Nếu thực tế cho thấy giỏ lớn, nhiều người cùng sửa độc lập, hoặc cần truy vấn xuyên các giỏ theo SKU, phải xem xét lại ranh giới.

### 4.1. Năm câu hỏi chọn đơn vị nguyên khối

1. **Co-read:** các trường có gần như luôn được đọc cùng nhau? Nếu chỉ 5% yêu cầu cần một blob lớn, đừng bắt 95% còn lại tải nó.
2. **Co-write:** các trường có thực sự cần thay đổi cùng nhau? Một giá trị duy nhất có thể đơn giản hóa thao tác thay toàn bộ, nhưng làm tăng tranh chấp khi cập nhật khác nhau.
3. **Vòng đời:** có cùng chủ sở hữu, TTL, quyền truy cập, điều kiện xóa và chính sách lưu giữ không?
4. **Giới hạn:** kích thước cực đại và tốc độ tăng trưởng có chấp nhận được theo hạn mức, băng thông, độ trễ và chi phí của hệ lưu trữ không?
5. **Nhất quán:** ràng buộc nào phải đúng ngay sau mỗi ghi? Chúng nằm toàn bộ trong một giá trị hay trải qua nhiều khóa / nguồn dữ liệu?

Ranh giới hợp lý thường là nơi dữ liệu **được đọc cùng nhau đủ thường xuyên**, **được thay đổi với mức tranh chấp chấp nhận được** và **có chung vòng đời**. Đây là quyết định đo từ workload, không chỉ nhìn cấu trúc JSON.

### 4.2. “Nguyên khối” khác “nguyên tử” như thế nào?

- **Nguyên khối về truy cập:** ứng dụng lấy một đơn vị logic bằng khóa `cart:shop_17:user_42`.
- **Nguyên tử của một lệnh ghi:** hệ thống có thể bảo đảm không quan sát thấy một nửa giá trị mới; phải kiểm tra hợp đồng của lệnh và sản phẩm đang dùng.
- **Nguyên tử của đọc–sửa–ghi:** cả chuỗi cần điều kiện phiên bản, thao tác máy chủ hoặc giao dịch để chống ghi mất dữ liệu.
- **Nguyên tử qua nhiều khóa:** thường cần cơ chế khác; không được suy ra từ tính nguyên tử trên một khóa.

Ví dụ, gộp `items` và `coupon` vào cùng một giá trị giúp đọc giỏ nhất quán theo một phiên bản. Nhưng **không** bảo đảm việc trừ tồn kho, tạo đơn hàng và ghi thanh toán thành một giao dịch xuyên các hệ thống.

## 5. Từ khóa tra cứu đến mô hình truy vấn

Mô hình khóa–giá trị tỏa sáng khi ứng dụng đã biết khóa. Hãy phân loại yêu cầu:

| Câu hỏi cần trả lời | Khóa đã biết? | Hướng thiết kế |
| --- | --- | --- |
| “Giỏ của user U tại shop S là gì?” | Có: `(S,U)` | Tra cứu trực tiếp một key. |
| “Phiên đăng nhập có token T là của ai?” | Có: `T` hoặc mã băm phù hợp | Một key gắn với session và TTL. |
| “Tìm toàn bộ user theo thành phố?” | Không | Cần chỉ mục truy vấn, document, quan hệ hoặc luồng phân tích phù hợp. |
| “Những giỏ nào có SKU A17?” | Không | Cần mô hình/ chỉ mục đọc khác; không quét toàn bộ key cho request thường xuyên. |
| “Mười đơn hàng mới nhất của user U?” | Có U, nhưng cần sắp thứ tự và lọc | Có thể cần khóa danh sách riêng, bảng có khóa sắp xếp, mô hình cột rộng hoặc quan hệ. |

Nếu có hai kiểu tìm kiếm bắt buộc, ví dụ `userId → profile` và `email → userId`, có thể tạo thêm khóa ánh xạ `email-index:<normalized-email> → userId`. Tuy nhiên, cập nhật email phải giữ **hai ánh xạ nhất quán** và bảo đảm email duy nhất khi có ghi đồng thời. Cơ sở dữ liệu quan hệ với unique constraint hoặc document database có chỉ mục unique có thể phù hợp hơn. Một phép `put` đơn giản vào hai key không tự sinh ra ràng buộc duy nhất.

**Tránh thiết kế dựa vào “quét hết key”** để đáp ứng truy vấn nghiệp vụ phổ biến. Một số sản phẩm hỗ trợ duyệt key phục vụ quản trị hoặc tác vụ nền, nhưng quét toàn bộ không thay thế được một chiến lược truy vấn có giới hạn và chỉ mục.

## 6. Ràng buộc, nhất quán và vòng đời

Một giá trị có cấu trúc vẫn cần bộ quy tắc rõ ràng.

### Ràng buộc trong một giá trị

Với giỏ hàng, ứng dụng phải kiểm tra:

- `quantity` là số nguyên dương, nằm trong giới hạn nghiệp vụ.
- Không có hai mục cùng `sku`; xóa mục khi số lượng trở về 0 nếu đó là quy tắc API.
- Số mục và kích thước tổng thể có giới hạn; dữ liệu thiếu/trường lạ được xử lý theo `schemaVersion`.
- ID khóa (shop, user) và ID trong nội dung, nếu lưu lặp, không được mâu thuẫn.
- Mỗi giá trị có schema được kiểm tra ở **biên ghi**, không chỉ khi hiển thị UI.

Cơ sở dữ liệu có thể coi JSON là byte và **không kiểm tra** những quy tắc này. Mã ứng dụng, hợp đồng API hoặc tính năng kiểm tra schema của sản phẩm phải chịu trách nhiệm.

### Ràng buộc qua nhiều giá trị

Ví dụ “chỉ có một người dùng sở hữu email X” hoặc “đơn hàng đã tạo thì số lượng tồn kho phải được đặt giữ chỗ” liên quan nhiều khóa và có thể nhiều dịch vụ. Cần lựa chọn có chủ đích giữa:

- Giao dịch/ghi có điều kiện được hệ quản trị hỗ trợ.
- Thiết kế lại ranh giới để các trường cần bất biến nằm cùng một đơn vị cập nhật.
- Quy trình nhiều bước có trạng thái, tính idempotent, kiểm tra và bù trừ nếu chấp nhận nhất quán cuối cùng.

Không hứa hẹn “tính nhất quán mạnh” hay “giao dịch đa khóa” chỉ vì hệ thống thuộc nhóm khóa–giá trị. Các mức bảo đảm thay đổi theo hệ quản trị, cấu hình và lệnh sử dụng.

### Hết hạn và độ bền

TTL phù hợp với phiên đăng nhập, cache hay giỏ tạm khi nghiệp vụ chấp nhận dữ liệu biến mất. Cần trả lời rõ:

- TTL bắt đầu từ lúc tạo hay được làm mới mỗi lần hoạt động?
- Sau khi hết hạn, thao tác đọc trả về gì và ứng dụng tạo lại trạng thái như thế nào?
- Khi kho chịu áp lực tài nguyên, hệ thống có thể loại bỏ dữ liệu trước TTL không?
- Dữ liệu cần lưu bền, sao lưu và phục hồi đến mức nào? Có chấp nhận mất giỏ sau sự cố không?

**Cache và nguồn dữ liệu chính** là hai vai trò kiến trúc khác nhau. Một kho khóa–giá trị có thể làm nơi lưu chính nếu khả năng bền vững, phục hồi và bảo đảm cập nhật đáp ứng yêu cầu; ngược lại, không nên đặt dữ liệu thanh toán duy nhất trong một bộ nhớ đệm có thể bị loại bỏ.

## 7. Kích thước, hiệu năng và phân vùng

Truy cập theo khóa thường giúp đường đọc đơn giản, nhưng tổng chi phí còn phụ thuộc thiết kế giá trị:

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Giá trị ngày càng lớn | Dồn lịch sử, danh sách vô hạn vào một key | Đặt giới hạn, phân trang bằng mô hình khác, tách dữ liệu lạnh |
| Ghi lại nhiều byte chỉ để đổi một trường | Hệ thống yêu cầu thay toàn bộ giá trị | Cân nhắc cập nhật trường nếu sản phẩm hỗ trợ hoặc đổi ranh giới |
| Xung đột và thử lại liên tục | Nhiều tác nhân cập nhật cùng một key | Đo độ tranh chấp; tách theo chủ thể ghi hoặc chuyển sang thao tác nguyên tử phù hợp |
| Khóa nóng | Một key nhận lượng lớn traffic dù có nhiều phân vùng | Thiết kế lại phân phối công việc; với bộ đếm cộng dồn có thể dùng shard và phép tổng hợp theo yêu cầu |
| Phải tải nhiều key cho một màn hình | Tách dữ liệu quá nhỏ | Gộp dữ liệu hay đọc cùng nhau, hoặc dùng batch/pipeline theo hệ quản trị |
| Khó truy vấn thống kê | Chỉ có đường truy cập theo key | Tạo read model/chỉ mục riêng hoặc đưa dữ liệu vào hệ phân tích |

Có thể ước lượng sơ bộ tải mạng của thao tác ghi cả giá trị:

```text
Dữ liệu ghi xấp xỉ ≈ số lần cập nhật/giây × kích thước giá trị trung bình

Ví dụ: 500 cập nhật/giây × 20 KiB/giá trị ≈ 9,8 MiB/giây dữ liệu payload.
```

Đây chỉ là **ước lượng lưu lượng payload một chiều**, chưa gồm replication, giao thức, log, nén, đọc trước khi ghi hoặc retry; không thể dùng trực tiếp để suy ra độ trễ hay công suất máy chủ. Đặc biệt cần quan sát phân vị kích thước (p95/p99), không chỉ trung bình, vì vài giá trị ngoại lệ có thể chi phối đuôi độ trễ.

Phân vùng theo hàm băm của khóa phân phối tốt **nhiều khóa độc lập**, nhưng không tự chia tải một **khóa duy nhất**. Không nên tạo thêm hậu tố ngẫu nhiên cho key nếu điều đó khiến ứng dụng mất khả năng tra cứu trực tiếp mà không có một chỉ mục tương ứng.

## 8. So sánh với các mô hình dữ liệu khác

Mục tiêu của mô hình hóa dữ liệu là chọn cấu trúc phục vụ truy vấn và quy tắc nghiệp vụ, không phải chọn mô hình nào “tốt nhất” cho mọi trường hợp.

| Mô hình | Truy cập điển hình | Khi phù hợp hơn |
| --- | --- | --- |
| **Khóa–giá trị** | Biết khóa → lấy/đổi một giá trị hoặc thực hiện thao tác được hỗ trợ | Session, cache, giỏ nhỏ, cấu hình theo ID, trạng thái tạm |
| **Document** | Đọc document theo ID và thường có truy vấn/chỉ mục trên thuộc tính bên trong | Hồ sơ có cấu trúc linh hoạt, tìm kiếm theo nhiều trường, cập nhật trường con (tùy hệ) |
| **Cột rộng (wide-column)** | Khóa phân vùng, hàng/cột và thứ tự trong phân vùng theo mô hình cụ thể | Nhật ký/sự kiện hoặc chuỗi thời gian cần truy cập theo thực thể và khoảng thời gian trên tập rất lớn |
| **Quan hệ** | PK/FK, join, điều kiện lọc, giao dịch và ràng buộc khai báo | Nhiều quan hệ nghiệp vụ, cập nhật đa bản ghi và yêu cầu toàn vẹn mạnh |
| **Đồ thị** | Nút, cạnh và duyệt quan hệ nhiều bước | Mối liên hệ thay đổi, truy vấn đường đi/độ gần |

Ví dụ, “50 lần đăng nhập mới nhất của user U” ban đầu trông giống `userId → value`, nhưng một chuỗi sự kiện có thể tăng vô hạn. Lưu toàn bộ lịch sử vào một blob khiến mỗi lần thêm sự kiện phải xử lý khối lớn và khó đọc theo khoảng thời gian. Một mô hình cột rộng với khóa phân vùng theo người dùng và bucket thời gian, cùng khóa sắp xếp theo thời điểm, có thể hợp lý hơn. Tuy nhiên, các tên “partition key”, “clustering key”, giới hạn phân vùng và cơ chế cập nhật **phụ thuộc sản phẩm**, không nên áp quy tắc của một cơ sở dữ liệu sang tất cả.

Có thể phối hợp mô hình: lưu giỏ đang hoạt động theo key; lưu đơn hàng chính thức trong hệ quan hệ; phát sự kiện đặt hàng tới hệ phân tích. Ranh giới được xác định theo nguồn dữ liệu có thẩm quyền, yêu cầu nhất quán và đường truy cập, không phải một nhãn NoSQL chung.

## 9. Phản ví dụ và cách sửa thiết kế

### Phản ví dụ A: một key chứa toàn bộ hoạt động của người dùng

```text
user:u_42 -> {
  profile: {...},
  cart: {...},
  orders: [hàng trăm nghìn mục],
  activityLog: [hàng triệu sự kiện]
}
```

Vấn đề: đọc hồ sơ phải tải lịch sử không liên quan; đơn hàng và hoạt động có vòng đời khác giỏ; ghi mọi sự kiện đụng cùng key; kích thước không có giới hạn rõ. Nên tách trạng thái giỏ nhỏ, hồ sơ, đơn hàng và chuỗi sự kiện thành những đơn vị với mô hình truy cập riêng. Có thể vẫn dùng khóa–giá trị cho phần thích hợp.

### Phản ví dụ B: mỗi trường một key không có lý do nghiệp vụ

```text
profile:u_42:name    -> "An"
profile:u_42:country -> "VN"
profile:u_42:locale  -> "vi"
```

Nếu màn hình nào cũng cần cả ba trường, chi phí điều phối nhiều key và rủi ro các trường lệch phiên bản có thể lớn hơn lợi ích tách chúng. Một giá trị `profile:u_42` nhỏ, có schema rõ ràng thường đơn giản hơn. Nếu mỗi trường có quyền truy cập hoặc tần suất ghi khác nhau, đánh giá lại với số liệu thực tế.

### Phản ví dụ C: chỉ có đường truy cập giỏ theo user, nhưng báo cáo cần tìm theo SKU

Không thể giải quyết yêu cầu “mọi giỏ chứa A17” bằng cách nói rằng JSON đã có trường SKU. Cần xây mô hình đọc riêng hoặc đổi công nghệ nếu đó là truy vấn cốt lõi. Nếu thêm chỉ mục ngược, phải định nghĩa cách cập nhật và sửa chữa chỉ mục khi có thay đổi giỏ, hết TTL hoặc ghi thất bại.

## 10. Quy trình thiết kế và kiểm chứng

Khi nhận yêu cầu mới, có thể làm theo trình tự sau:

1. **Viết câu hỏi nghiệp vụ thành truy vấn cụ thể.** Đầu vào của mỗi thao tác là gì? Có biết khóa không? Có cần lọc, sắp xếp, phân trang hay join?
2. **Vẽ ranh giới đơn vị truy cập.** Nhóm những trường thường đọc và quản lý vòng đời cùng nhau; chú ý dữ liệu có khả năng tăng không giới hạn.
3. **Liệt kê những thay đổi có thể diễn ra đồng thời.** Xác định các bất biến cần bảo vệ, như “mỗi SKU chỉ có một dòng” hoặc “số lượng không âm”.
4. **Định nghĩa khóa và giá trị.** Quy tắc định danh, tính duy nhất, cấu trúc schema, giới hạn kích thước, version, TTL và chính sách xóa.
5. **Chọn cơ chế bảo đảm.** So sánh CAS, cập nhật nguyên tử, giao dịch đa key và điều kiện nhất quán mà hệ thống thật sự hỗ trợ.
6. **Ước lượng tải và kiểm chứng bằng workload.** Ghi rõ số lượng key, tần suất và phân bố đọc/ghi, kích thước p95/p99, số lần retry, độ trễ và tỉ lệ miss.
7. **Kiểm tra thay đổi và vận hành.** Thử dữ liệu hết hạn, đọc khi key không tồn tại, nâng phiên bản schema, phục hồi sau sự cố và cập nhật đồng thời; thiết kế kế hoạch migrate nếu thay ranh giới.

### Bộ kiểm thử tối thiểu cho ví dụ giỏ hàng

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Đọc key chưa tồn tại | Trả giỏ rỗng hoặc trạng thái “không có giỏ” theo hợp đồng API, không gây lỗi dữ liệu mơ hồ. |
| Hai thiết bị sửa cùng `revision` | Không mất cập nhật; một thao tác thành công, thao tác còn lại thử lại hoặc nhận xung đột có kiểm soát. |
| Thêm hai lần cùng SKU | Không xuất hiện hai dòng SKU; số lượng tuân quy tắc API. |
| Vượt số lượng mục hoặc kích thước cho phép | Từ chối rõ ràng hoặc chuyển sang mô hình phù hợp theo chính sách. |
| Hết TTL | Hệ thống xử lý trường hợp không còn giỏ theo nghiệp vụ; không cho rằng `updatedAt` tự thực thi TTL. |
| Schema cũ | Có đường đọc/migrate an toàn; không làm mất dữ liệu do thay đổi định dạng âm thầm. |
| Xác nhận đơn hàng | Kiểm tra lại giá/tồn kho, áp dụng ràng buộc đặt hàng và tính idempotent ngoài giá trị giỏ. |

## 11. Bài tập vận dụng có hướng dẫn

**Tình huống 1 — Cờ tính năng theo tenant.** Mỗi request biết `tenantId`, cần lấy 10–20 cờ tính năng của tenant. Cờ chỉ đổi vài lần mỗi ngày và được phát hành cùng phiên bản cấu hình.

- **Gợi ý mô hình:** `features:<tenantId> → {schemaVersion, flags, publishedAt}`. Vì đọc cùng nhau, thay đổi không thường xuyên và cùng vòng đời, một giá trị là lựa chọn hợp lý.
- **Điều cần bổ sung:** nguồn cấu hình có thẩm quyền, cách cache bị vô hiệu khi xuất bản bản mới, giới hạn kích thước, kiểm soát quyền truy cập.

**Tình huống 2 — Nhật ký thiết bị.** Mỗi thiết bị gửi một bản ghi mỗi giây, hệ thống cần hiển thị 1.000 bản ghi gần nhất và lọc theo khoảng thời gian.

- **Không nên:** nối mọi bản ghi vào một value `device:<deviceId>` không giới hạn; giá trị sẽ tăng, ghi tranh chấp và rất khó truy vấn theo khoảng thời gian.
- **Hướng phù hợp:** dữ liệu chuỗi thời gian hoặc mô hình cột rộng phân vùng theo thiết bị và khoảng thời gian; chọn bucket và khóa sắp xếp sau khi đo lưu lượng và giới hạn cụ thể của hệ quản trị.

**Tình huống 3 — Giỏ hàng đổi số lượng quá thường xuyên.** Hệ thống ban đầu lưu cả giỏ trong một key. Sau khi triển khai, p99 cập nhật tăng cao, retry do xung đột nhiều và một số giỏ có hàng nghìn mục.

- **Cách phân tích:** đo phân bố kích thước và mức tranh chấp từng key; xác định thao tác nào thực sự cần đọc cả giỏ.
- **Hướng thay đổi:** áp giới hạn giỏ; dùng cập nhật từng mục nếu sản phẩm cho phép; hoặc tách item và dùng mô hình/chỉ mục đủ bảo đảm. Không tách máy móc nếu chi phí tải toàn giỏ và xóa đồng bộ tăng quá mức.

## Tổng kết kiến thức

Một mô hình khóa–giá trị được thiết kế tốt bắt đầu từ **mẫu truy cập bằng khóa đã biết** và **ranh giới dữ liệu thật sự cần đi cùng nhau**. Gộp dữ liệu giúp đọc thuận tiện và có thể đơn giản hóa vòng đời; tách dữ liệu giúp thay đổi độc lập, tránh tăng kích thước và giảm tranh chấp ở một số workload. Quyết định đúng phải xét cả truy vấn, cập nhật đồng thời, ràng buộc nghiệp vụ, TTL, độ bền và vận hành.

Khi đánh giá thiết kế, hãy tự trả lời ba câu: **Ứng dụng biết khóa nào? Một lần truy cập cần chính xác phần nào? Điều gì bắt buộc nhất quán sau mỗi thay đổi?** Nếu một yêu cầu không thể được đáp ứng bằng tra cứu khóa với chi phí chấp nhận được, đó là tín hiệu cần một mô hình truy cập khác hoặc một công nghệ lưu trữ khác.
