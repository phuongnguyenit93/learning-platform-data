# Viết mô tả nêu chức năng, điều kiện dùng và giới hạn

Khi Spring AI cung cấp một phương thức Java cho mô hình ngôn ngữ, tên và mô tả của công cụ trở thành một phần hợp đồng mà mô hình dùng để quyết định có nên gọi công cụ đó hay không. Mô hình không nhìn thấy toàn bộ ý định của người viết mã. Nó dựa vào tên công cụ, mô tả công cụ và schema tham số được gửi trong yêu cầu để phân biệt các khả năng gần giống nhau.

Vì vậy, một mô tả tốt cần nói rõ công cụ làm gì, nên được dùng trong tình huống nào và giới hạn của nó. Mô tả tham số cũng cần giải thích dữ liệu mà ứng dụng mong đợi, chẳng hạn mã định danh, đơn vị, định dạng thời gian hoặc tập giá trị hợp lệ. `@Tool` và `@ToolParam` cho phép đặt những thông tin này ngay cạnh phương thức và tham số Java.

Mô tả giúp mô hình chọn và tạo yêu cầu phù hợp; nó không thực thi quy tắc nghiệp vụ, không xác thực người dùng và không bảo đảm mô hình luôn chọn đúng. Ứng dụng vẫn phải kiểm tra đầu vào, quyền truy cập và điều kiện nghiệp vụ khi callback thực thi.

## Mô hình cần biết gì trước khi gọi công cụ?

Một định nghĩa công cụ thường cung cấp ba nhóm thông tin:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Tên công cụ | Đây là khả năng nào? | `getOrderStatus` |
| Mô tả công cụ (`@Tool`) | Công cụ làm gì, khi nào nên dùng và không xử lý việc gì? | Tra cứu trạng thái đơn hàng hiện tại; dùng khi người dùng hỏi tiến độ của một đơn đã tạo; không cập nhật hoặc hủy đơn. |
| Schema và mô tả tham số (`@ToolParam`) | Cần những đối số nào, ý nghĩa và định dạng của chúng là gì? | `orderId` là mã đơn hàng do hệ thống cấp, không phải tên người mua. |

Mô tả công cụ giúp mô hình chọn giữa các công cụ. Mô tả tham số giúp mô hình điền đúng từng trường sau khi đã chọn. Hai phần này bổ sung cho nhau; không nên dồn mọi thông tin vào một mô tả dài rồi để tham số chỉ có tên kỹ thuật.

Ví dụ, trong một ứng dụng bán hàng có `getOrderStatus`, `searchProducts` và `cancelOrder`, câu “Xử lý đơn hàng” quá chung chung. Mô hình không biết công cụ đọc trạng thái, tìm sản phẩm hay hủy giao dịch. Một mô tả có hành động cụ thể và điều kiện dùng giúp giảm sự nhập nhằng.

## Viết mô tả cho `@Tool`

Trong Spring AI, `@Tool` đánh dấu phương thức có thể được cung cấp như một công cụ. Bạn có thể khai báo tên và mô tả bằng annotation, ví dụ:

```java
@Tool(
    name = "getOrderStatus",
    description = """
        Tra cứu trạng thái hiện tại của một đơn hàng.
        Dùng khi người dùng hỏi tiến độ xử lý hoặc giao hàng của đơn đã tạo.
        Chỉ đọc trạng thái và thời điểm cập nhật gần nhất; không sửa, hủy
        hoặc tạo đơn hàng.
        """
)
public OrderStatusView getOrderStatus(
        @ToolParam(description = "Mã đơn hàng do hệ thống cấp") String orderId) {
    return orderQueryService.getStatus(orderId);
}
```

Ví dụ dùng Java text block để dễ đọc. Nếu phiên bản Java của dự án hoặc cách định dạng mã không hỗ trợ text block, hãy dùng chuỗi thông thường. Các thuộc tính annotation và khả năng xử lý của framework cần được đối chiếu với phiên bản Spring AI mà dự án đang dùng.

Một mô tả công cụ hữu ích thường có bốn phần:

1. **Chức năng:** bắt đầu bằng động từ và nêu rõ đối tượng được xử lý, ví dụ “Tra cứu trạng thái đơn hàng” hoặc “Tìm sản phẩm theo tên và khoảng giá”.
2. **Điều kiện dùng:** mô tả loại câu hỏi hoặc nhu cầu mà công cụ giải quyết, ví dụ “Dùng khi người dùng hỏi trạng thái của một đơn đã tạo”.
3. **Phạm vi:** nêu loại dữ liệu hoặc đối tượng mà công cụ xử lý, ví dụ “Chỉ tìm trong danh mục sản phẩm đang kinh doanh”.
4. **Giới hạn:** nói rõ hành động mà công cụ không thực hiện hoặc điều kiện khiến nó không phù hợp, ví dụ “Không cập nhật tồn kho hoặc tạo đơn hàng”.

Không phải mô tả nào cũng cần bốn câu riêng. Với công cụ đơn giản, một hoặc hai câu có thể đủ. Mục tiêu là giúp mô hình phân biệt được công cụ với các lựa chọn khác bằng thông tin cụ thể, không phải tạo một đoạn văn dài.

### So sánh mô tả mơ hồ và mô tả có thể sử dụng

| Mô tả chưa tốt | Vấn đề | Mô tả rõ hơn |
|---|---|---|
| `Xử lý đơn hàng` | Không nói rõ hành động đọc hay ghi. | `Tra cứu trạng thái hiện tại của đơn hàng theo mã đơn.` |
| `Tìm dữ liệu` | Không xác định loại dữ liệu và điều kiện dùng. | `Tìm sản phẩm đang kinh doanh theo từ khóa tên và khoảng giá.` |
| `Cập nhật tài khoản` | Không nêu trường nào được sửa và giới hạn. | `Cập nhật địa chỉ giao hàng mặc định của tài khoản hiện tại; không đổi email hoặc thông tin xác thực.` |
| `Kiểm tra giao hàng` | Không nói cần mã nào hoặc trả thông tin gì. | `Tra cứu các mốc vận chuyển mới nhất của một đơn hàng đã được bàn giao cho đơn vị vận chuyển.` |

### Đặt ranh giới giữa các công cụ gần nhau

Khi nhiều công cụ có tên hoặc chức năng tương tự, mô tả cần chỉ ra điểm phân biệt. Ví dụ:

```java
@Tool(
    name = "getOrderStatus",
    description = "Tra cứu trạng thái xử lý hiện tại của đơn hàng theo mã đơn. "
            + "Dùng cho câu hỏi đơn đã xác nhận, đang chuẩn bị hay đã hoàn tất. "
            + "Không trả về lộ trình vận chuyển chi tiết."
)
public OrderStatusView getOrderStatus(
        @ToolParam(description = "Mã đơn hàng do hệ thống cấp") String orderId) {
    return orderQueryService.getStatus(orderId);
}

@Tool(
    name = "getShipmentTracking",
    description = "Tra cứu các mốc vận chuyển và thời điểm giao dự kiến "
            + "của đơn đã được bàn giao cho đơn vị vận chuyển. "
            + "Dùng khi người dùng hỏi vị trí hoặc tiến độ giao hàng; "
            + "không thay đổi trạng thái đơn."
)
public ShipmentTrackingView getShipmentTracking(
        @ToolParam(description = "Mã vận đơn do đơn vị vận chuyển cấp") String trackingNumber) {
    return shipmentQueryService.getTracking(trackingNumber);
}
```

Ở đây, công cụ thứ nhất phục vụ trạng thái nghiệp vụ của đơn hàng; công cụ thứ hai phục vụ thông tin vận chuyển. Việc nêu rõ khác biệt giúp mô hình chọn đúng khả năng hơn so với hai mô tả đều chỉ ghi “Kiểm tra đơn hàng”.

## Viết mô tả tham số bằng `@ToolParam`

`@ToolParam` bổ sung ý nghĩa cho từng tham số mà mô hình cần cung cấp. Một mô tả tham số nên giúp trả lời:

- Giá trị đại diện cho điều gì trong nghiệp vụ?
- Lấy giá trị từ đâu hoặc định danh theo quy tắc nào?
- Định dạng, đơn vị, múi giờ hoặc tập giá trị được chấp nhận là gì?
- Có thể bỏ qua trường này trong trường hợp nào?

Ví dụ:

```java
@Tool(
    name = "searchProducts",
    description = "Tìm sản phẩm đang kinh doanh theo tên và khoảng giá. "
            + "Dùng khi người dùng muốn khám phá hoặc so sánh sản phẩm; "
            + "không tạo đơn hàng."
)
public List<ProductSummary> searchProducts(
        @ToolParam(description = "Từ khóa tên sản phẩm; không phải mã SKU") String keyword,
        @ToolParam(description = "Giá thấp nhất, tính bằng VND") BigDecimal minPrice,
        @ToolParam(description = "Giá cao nhất, tính bằng VND") BigDecimal maxPrice) {
    return productService.search(keyword, minPrice, maxPrice);
}
```

Các mô tả `minPrice` và `maxPrice` nói rõ đơn vị tiền tệ. Nếu không ghi đơn vị, mô hình có thể tạo giá trị theo một loại tiền khác hoặc hiểu sai quy mô. Với tham số ngày giờ, hãy nói rõ định dạng và múi giờ; với enum, hãy giải thích ý nghĩa từng giá trị nếu tên kỹ thuật không tự giải thích được.

Tránh mô tả lặp lại tên biến. “Giá thấp nhất” hữu ích hơn “minPrice là minPrice”. Nếu tham số có quy tắc nghiệp vụ đặc biệt, hãy mô tả ngắn gọn quy tắc đó và vẫn kiểm tra lại trong mã thực thi.

## Tham số bắt buộc, tùy chọn và giá trị null

Theo API Spring AI hiện hành, `@ToolParam` có thuộc tính `required`; mặc định là `true`. Khi tham số có thể được bỏ qua, bạn có thể khai báo `required = false` và mô tả rõ khi nào được bỏ qua. Hãy kiểm tra chữ ký annotation của release line dự án nếu đang dùng phiên bản khác.

```java
@Tool(
    name = "searchProducts",
    description = "Tìm sản phẩm đang kinh doanh theo từ khóa và bộ lọc tùy chọn."
)
public List<ProductSummary> searchProducts(
        @ToolParam(description = "Từ khóa tên hoặc đặc điểm sản phẩm") String keyword,
        @ToolParam(
            description = "Giá tối đa bằng VND; bỏ qua nếu người dùng không nêu ngân sách",
            required = false
        ) BigDecimal maxPrice) {

    return productService.search(keyword, maxPrice);
}
```

Khi thiết kế tham số tùy chọn, cần phân biệt ba tình huống:

| Tình huống | Ý nghĩa | Cách xử lý trong ứng dụng |
|---|---|---|
| Trường bắt buộc | Không có giá trị thì không thể thực hiện yêu cầu. | Đánh dấu bắt buộc và từ chối nếu dữ liệu thiếu. |
| Trường tùy chọn bị bỏ qua | Người dùng không đưa ra bộ lọc hoặc không cần điều kiện đó. | Dùng giá trị mặc định hoặc bỏ qua bộ lọc theo quy tắc đã định nghĩa. |
| Trường được gửi với giá trị null | Có trường trong dữ liệu nhưng giá trị không có. | Quy định rõ null có tương đương bỏ qua hay là dữ liệu không hợp lệ. |

`required = false` mô tả tính tùy chọn trong schema. Nó không tự quyết định giá trị mặc định của Java, không bảo đảm mọi provider gửi cùng một biểu diễn cho trường bị thiếu và trường null, cũng không thay thế kiểm tra null trong phương thức. Hãy thiết kế kiểu tham số và xử lý giá trị thiếu phù hợp với converter, schema và phiên bản Spring AI đang dùng.

Với tham số tùy chọn, cần cân nhắc:

- Nếu bỏ qua trường, phương thức có thể thực hiện một truy vấn rộng hơn không? Có cần giới hạn mặc định để tránh trả quá nhiều dữ liệu không?
- Nếu hai tham số phải xuất hiện cùng nhau, ứng dụng có kiểm tra quan hệ đó không? Ví dụ `minPrice` không được lớn hơn `maxPrice`.
- Nếu trường null có ý nghĩa khác với trường bị thiếu, schema hoặc DTO có biểu diễn được khác biệt đó không?
- Có nên tách một công cụ thành hai công cụ đơn giản hơn nếu quá nhiều tham số tùy chọn khiến mô hình khó tạo đối số?

## Đặt tên công cụ và tham số

Tên là tín hiệu ngắn giúp mô hình nhận diện chức năng; mô tả cung cấp ngữ cảnh đầy đủ hơn. Hãy dùng tên cụ thể, ổn định và duy nhất trong tập công cụ được cung cấp cho một yêu cầu.

| Nên dùng | Tránh dùng | Lý do |
|---|---|---|
| `getOrderStatus` | `processOrder` | Tên đầu tiên chỉ rõ thao tác đọc trạng thái; tên sau không rõ là đọc hay ghi. |
| `searchProducts` | `doSearch` | Tên đầu tiên chỉ rõ đối tượng được tìm. |
| `cancelOrder` | `updateOrder` | Tên đầu tiên nêu chính xác hành động có tác động nghiệp vụ. |
| `trackingNumber` | `value` | Tên đầu tiên cho biết loại định danh cần truyền. |

Khi cần giữ hợp đồng ổn định qua các lần đổi tên phương thức Java, hãy khai báo `name` tường minh trong `@Tool`. Tên được gửi đến model provider có thể chịu quy tắc ký tự hoặc độ dài riêng; kiểm tra giới hạn của provider và phiên bản Spring AI thay vì giả định mọi provider có cùng quy tắc.

Không dùng tên hoặc mô tả để nhúng dữ liệu thay đổi theo người dùng, API key, thông tin xác thực, prompt bí mật hay dữ liệu riêng tư. Định nghĩa công cụ thường được gửi tới model provider như một phần yêu cầu hội thoại. Chỉ đưa thông tin cần thiết để mô hình hiểu cách sử dụng công cụ.

## Mô tả không thay thế validation và phân quyền

Đây là ranh giới quan trọng nhất khi viết công cụ cho hệ thống nghiệp vụ.

Giả sử mô tả nói “Chỉ tra cứu đơn hàng của người dùng hiện tại”. Câu này giúp mô hình hiểu phạm vi, nhưng mô hình vẫn có thể gửi một `orderId` thuộc tài khoản khác. Phương thức phải lấy danh tính từ ngữ cảnh đáng tin cậy do ứng dụng truyền vào và dịch vụ phải kiểm tra quyền trên chính đơn hàng đó.

```java
@Tool(
    name = "getMyOrderStatus",
    description = "Tra cứu trạng thái đơn hàng thuộc tài khoản người dùng hiện tại. "
            + "Dùng khi người dùng hỏi tiến độ của đơn đã tạo; "
            + "không truy vấn đơn của tài khoản khác và không sửa dữ liệu."
)
public OrderStatusView getMyOrderStatus(
        @ToolParam(description = "Mã đơn hàng do hệ thống cấp") String orderId,
        ToolContext toolContext) {

    String userId = (String) toolContext.getContext().get("userId");
    return orderQueryService.findStatusForUser(orderId, userId);
}
```

Trong ví dụ, `orderId` là đối số mô hình đề xuất. `userId` đến từ `ToolContext`, được ứng dụng tạo từ danh tính đã xác thực và không phải trường mà mô hình được quyền chọn. Service vẫn cần kiểm tra quyền truy cập; không nên dựa vào việc mô tả đã nói rõ phạm vi.

Tương tự, các giới hạn sau phải được thực thi bằng mã:

- Giới hạn số kết quả, khoảng ngày, số tiền và kích thước dữ liệu.
- Kiểm tra định dạng, miền giá trị, sự tồn tại của tài nguyên và quan hệ giữa các tham số.
- Kiểm tra quyền theo người dùng, tenant, vai trò và tài nguyên cụ thể.
- Yêu cầu xác nhận cho thao tác có tác động như thanh toán, hủy đơn hoặc thay đổi dữ liệu quan trọng.
- Giới hạn thời gian, số lần gọi, tần suất và mức đồng thời.

Mô tả là hướng dẫn cho mô hình; schema là hợp đồng cấu trúc; validation và authorization trong ứng dụng mới là nơi bảo vệ hệ thống.

## Giới hạn của mô tả công cụ

Ngay cả khi mô tả rõ ràng, vẫn có những giới hạn cần tính đến:

1. **Mô hình có thể không gọi công cụ.** Mô hình có thể trả lời trực tiếp, hỏi lại người dùng hoặc chọn công cụ khác. Ứng dụng không được giả định mọi yêu cầu đều dẫn tới thực thi.
2. **Mô hình có thể hiểu sai mô tả.** Hai công cụ gần nghĩa, mô tả mâu thuẫn hoặc tên không rõ ràng làm tăng nguy cơ chọn sai.
3. **Schema không diễn tả được mọi quy tắc nghiệp vụ.** Điều kiện phụ thuộc trạng thái hệ thống, quyền người dùng hoặc quan hệ phức tạp giữa trường thường phải được kiểm tra trong mã.
4. **Provider có thể diễn giải schema khác nhau.** Mức hỗ trợ kiểu dữ liệu, trường optional, enum, object lồng nhau và giới hạn tên/mô tả phụ thuộc model provider và phiên bản.
5. **Mô tả tiêu tốn ngữ cảnh.** Mô tả quá dài làm tăng dữ liệu gửi cho mô hình và khiến các điểm quan trọng khó nổi bật. Giữ thông tin ngắn, có cấu trúc và không lặp lại.
6. **Mô tả không phải ranh giới bảo mật.** Người dùng có thể yêu cầu mô hình bỏ qua hướng dẫn hoặc tạo đối số không hợp lệ; callback phải coi mọi đối số từ mô hình là dữ liệu đầu vào chưa đáng tin cậy.

Đừng cố giải quyết mọi giới hạn bằng cách thêm thật nhiều câu vào description. Hãy đơn giản hóa tập công cụ, đặt tên phân biệt, tách trách nhiệm và chuyển quy tắc quan trọng về mã ứng dụng.

## Kiểm thử chất lượng mô tả

Mô tả cần được kiểm thử cùng hành vi gọi công cụ. Một unit test cho phương thức chỉ xác nhận logic Java; nó không chứng minh mô hình sẽ chọn đúng công cụ dựa trên description.

Hãy tạo một bộ câu hỏi đại diện cho từng công cụ:

| Loại tình huống | Ví dụ câu hỏi | Điều cần quan sát |
|---|---|---|
| Đúng điều kiện dùng | “Đơn DH-100 đang ở trạng thái nào?” | Mô hình chọn `getOrderStatus` và tạo đúng `orderId`. |
| Gần nghĩa nhưng thuộc công cụ khác | “Đơn của tôi đang ở đâu trên đường giao?” | Mô hình chọn công cụ theo dõi vận chuyển thay vì chỉ tra trạng thái nghiệp vụ. |
| Ngoài phạm vi | “Hãy hủy đơn này.” khi chỉ cung cấp công cụ tra cứu | Mô hình không giả vờ đã hủy đơn và không dùng nhầm công cụ đọc. |
| Thiếu dữ liệu bắt buộc | “Kiểm tra đơn hàng giúp tôi.” nhưng không có mã đơn | Mô hình hỏi lại mã đơn hoặc không gọi công cụ với đối số thiếu. |
| Trường tùy chọn | “Tìm sản phẩm dưới 500.000 VND.” | Mô hình cung cấp bộ lọc phù hợp và để các trường không được nêu ở trạng thái bỏ qua hợp lệ. |
| Đối số không hợp lệ | Mã đơn sai định dạng hoặc khoảng giá âm | Ứng dụng từ chối dữ liệu và trả lỗi có kiểm soát. |
| Truy cập trái quyền | Mã đơn thuộc người dùng khác | Ứng dụng từ chối dù mô hình đã tạo được tool call. |

Khi đánh giá, ghi lại câu hỏi, tập công cụ được cung cấp, tool call mà mô hình tạo ra, đối số, kết quả thực thi và câu trả lời cuối. Theo dõi tỷ lệ chọn đúng công cụ, tỷ lệ cần hỏi lại, lỗi schema và lỗi nghiệp vụ. Thử với model provider thực tế vì hành vi chọn công cụ có thể khác giữa các model.

Nếu hai công cụ liên tục bị chọn nhầm, hãy xem lại ranh giới chức năng và bộ câu hỏi kiểm thử. Có thể cần đổi tên, viết lại điều kiện dùng, mô tả giới hạn rõ hơn hoặc tách một công cụ đang làm quá nhiều việc.

## Quy trình viết và rà soát một định nghĩa công cụ

Trước khi đưa phương thức vào tập công cụ, hãy đi qua các bước sau:

1. Xác định một hành động nghiệp vụ rõ ràng mà phương thức thực hiện.
2. Chọn tên duy nhất, mô tả ngắn chức năng và điều kiện gọi.
3. Viết giới hạn quan trọng để phân biệt với công cụ gần nghĩa.
4. Với mỗi tham số, mô tả ý nghĩa, định dạng, đơn vị và tính bắt buộc.
5. Xác định thông tin nào phải đến từ `ToolContext` hoặc nguồn đáng tin cậy khác thay vì từ mô hình.
6. Viết validation và authorization trong mã thực thi cho mọi điều kiện có ảnh hưởng đến dữ liệu hoặc nghiệp vụ.
7. Thử câu hỏi đúng phạm vi, ngoài phạm vi, thiếu dữ liệu và dễ nhầm với công cụ khác.
8. Kiểm tra lại schema thực tế được tạo và hành vi trên model provider đang dùng.

## Bài tập thực hành

Giả sử bạn xây dựng hai công cụ cho hệ thống bán hàng: một công cụ tra cứu trạng thái đơn và một công cụ tìm sản phẩm.

1. Viết `@Tool` cho từng phương thức với tên khác nhau và mô tả có chức năng, điều kiện dùng, giới hạn.
2. Dùng `@ToolParam` để mô tả mã đơn, từ khóa tìm kiếm và khoảng giá; ghi rõ đơn vị tiền tệ.
3. Đánh dấu bộ lọc giá là tùy chọn nếu nghiệp vụ cho phép, rồi xử lý trường bị thiếu hoặc null trong phương thức.
4. Thêm một câu hỏi có thể khiến mô hình nhầm giữa trạng thái đơn và theo dõi vận chuyển; sửa mô tả để ranh giới rõ hơn.
5. Kiểm tra quyền truy cập đơn hàng trong service bằng danh tính lấy từ context.
6. Chạy bộ câu hỏi kiểm thử và ghi nhận công cụ, đối số, kết quả mà mô hình tạo ra.

Bạn hoàn thành khi một người khác có thể đọc tên, description và mô tả tham số để hiểu công cụ làm gì, khi nào nên gọi, cần dữ liệu nào và giới hạn ở đâu; đồng thời ứng dụng vẫn từ chối được đầu vào sai hoặc yêu cầu vượt quyền.

## Danh sách kiểm tra

- [ ] Tên công cụ thể hiện một hành động cụ thể và duy nhất trong tập được cung cấp.
- [ ] Description nêu chức năng, điều kiện dùng và giới hạn quan trọng.
- [ ] Các công cụ gần nghĩa có mô tả phân biệt được.
- [ ] Mỗi `@ToolParam` giải thích ý nghĩa nghiệp vụ, định dạng và đơn vị khi cần.
- [ ] Trường bắt buộc và tùy chọn được khai báo đúng; mã xử lý giá trị thiếu và null.
- [ ] Không đưa secret, dữ liệu riêng tư hoặc quy tắc bảo mật chỉ dựa vào description.
- [ ] Validation, authorization và giới hạn tài nguyên được thực thi trong ứng dụng.
- [ ] Có kiểm thử câu hỏi đúng phạm vi, ngoài phạm vi, thiếu dữ liệu và dễ nhầm.
- [ ] Schema và hành vi đã được kiểm tra với phiên bản Spring AI và model provider đang dùng.

Một định nghĩa công cụ tốt là hợp đồng ngắn gọn, dễ phân biệt và có thể kiểm chứng. `@Tool` giúp mô hình hiểu khả năng mà ứng dụng cung cấp; `@ToolParam` giúp mô hình tạo đối số có ý nghĩa. Phần thực thi của ứng dụng vẫn là nơi quyết định dữ liệu nào được chấp nhận và hành động nào được phép xảy ra.
