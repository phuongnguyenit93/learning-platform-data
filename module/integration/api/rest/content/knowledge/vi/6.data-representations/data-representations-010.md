# Quy ước tên trường, cấu trúc lồng và biểu diễn quan hệ

Một REST API cần giúp client hiểu tên trường có nghĩa gì, object lồng thuộc về resource nào và cách truy cập dữ liệu liên quan. JSON hợp lệ về cú pháp chưa đủ để tạo ra một hợp đồng dễ sử dụng và ổn định.

Trong module `INTEGRATION_API_REST`, bài này tập trung vào hợp đồng biểu diễn dữ liệu giữa client và server. Ví dụ dùng hệ thống đặt hàng và có thể triển khai bằng Java/Spring hoặc công nghệ tương đương. REST không bắt buộc JSON, `camelCase` hay một cách biểu diễn quan hệ duy nhất. Những lựa chọn dưới đây là quy ước của API ví dụ, cần được công bố trong tài liệu hợp đồng.

Sau bài học, bạn có thể đặt tên trường nhất quán; phân biệt giá trị lồng với resource độc lập; chọn giữa ID, bản tóm tắt và liên kết; thiết kế riêng request và response; nhận diện thay đổi cấu trúc có thể làm hỏng client.

## 1. Biểu diễn công khai không phải cấu trúc lưu trữ

Resource là khái niệm mà API cung cấp, chẳng hạn đơn hàng tại `/orders/ord_8f2`. JSON trả về là một biểu diễn của resource tại thời điểm đọc. Nó không nhất thiết giống bản ghi database hoặc đối tượng ORM.

Ví dụ, bảng có `order_id`, `customer_fk`, `created_at` và `risk_score`. API có thể công bố `id`, một object `customer`, `createdAt`, đồng thời không công bố điểm đánh giá rủi ro. Database đổi tên cột không cần buộc client đổi code nếu hợp đồng API giữ nguyên.

| Khía cạnh | Cấu trúc nội bộ | Hợp đồng API |
| --- | --- | --- |
| Tên | Theo database hoặc quy ước code | Theo khái niệm mà client sử dụng |
| Quan hệ | Khóa ngoại, bảng nối, tham chiếu object | ID, summary, liên kết hoặc collection |
| Thuộc tính | Có thể gồm dữ liệu vận hành nhạy cảm | Chỉ công bố trường nằm trong hợp đồng và được phép đọc |
| Thay đổi | Theo nhu cầu triển khai | Phải xét khả năng tương thích với client |

Mô hình miền có một đồ thị quan hệ lớn không có nghĩa response phải chứa toàn bộ đồ thị. Mỗi biểu diễn cần một ranh giới dữ liệu có chủ đích.

## 2. Quy ước tên trường

### 2.1. Chọn một kiểu viết

API ví dụ dùng `camelCase` cho các trường JSON:

```json
{
  "id": "ord_8f2",
  "customerId": "cus_42",
  "createdAt": "2026-11-17T08:30:00Z",
  "totalAmount": "500000",
  "currency": "VND"
}
```

Một API có thể dùng `snake_case` nếu đó là quy ước chung. Điều quan trọng là áp dụng nhất quán ở request, response và các object con. Tránh trộn `customer_id`, `createdAt`, `TotalAmount` trong một biểu diễn.

Tên JSON không buộc phải trùng tên thuộc tính Java. Nếu khác nhau, ánh xạ rõ tại DTO hoặc lớp chuyển đổi. Không để việc đổi tên property nội bộ vô tình thay hợp đồng công khai.

### 2.2. Đặt tên theo nghĩa nghiệp vụ

| Mục đích | Tên gợi ý | Tên nên tránh | Lý do |
| --- | --- | --- | --- |
| Định danh resource hiện tại | `id` | `pk`, `rowKey` | Không gắn client với cách lưu trữ |
| Tham chiếu bằng định danh | `customerId` | `customer` là chuỗi nhưng không được giải thích | Phân biệt ID với object |
| Object liên quan | `customer` | `customerDataObject` | Dùng danh từ nghiệp vụ |
| Collection | `items`, `members` | `itemListArray` | Tên số nhiều đã thể hiện tập phần tử |
| Trạng thái nhiều giá trị | `status` | `isDone` | Boolean không biểu đạt đủ các bước nghiệp vụ |
| Khả năng thao tác | `canCancel` | `flag1` | Thể hiện điều client cần biết |
| Thời điểm | `createdAt`, `expiresAt` | `date`, `time` | Phân biệt sự kiện và loại giá trị |
| Đại lượng có đơn vị cố định | `timeoutSeconds` | `timeout` | Tránh client tự đoán đơn vị |

Tên ngắn chỉ có ích khi vẫn rõ nghĩa. `amount` bên trong object `price` có thể đủ rõ; ở cấp gốc với nhiều khoản phí, nó thường cần tên cụ thể hơn.

Với boolean, có thể chọn `active`, `hasAttachments`, `canCancel` tùy nghĩa, không cần ép mọi trường có tiền tố `is`. Tránh phủ định kép như `isNotDisabled`. Phân biệt trạng thái đã lưu với quyền thao tác hiện tại: `canCancel` có thể phụ thuộc người gọi, quyền và trạng thái đơn. Server vẫn phải kiểm tra lại khi nhận yêu cầu hủy.

### 2.3. Tên cần đi cùng kiểu, đơn vị và miền giá trị

- **ID:** bài này dùng chuỗi opaque; client lưu và gửi lại, không phân tích tiền tố để suy nghiệp vụ hoặc thực hiện phép tính. Đây là lựa chọn hợp đồng, không phải yêu cầu của REST. ID khó đoán không thay thế kiểm tra quyền.
- **Thời điểm:** dùng chuỗi có UTC hoặc offset, chẳng hạn `2026-11-17T08:30:00Z`. Phân biệt với ngày thuần túy `deliveryDate: "2026-11-20"`, vốn chưa xác định một thời điểm trong múi giờ.
- **Tiền:** xác định đơn vị và độ chính xác. Ví dụ dùng chuỗi thập phân `"500000"` cùng `currency: "VND"`. Một API khác có thể chọn số nguyên theo đơn vị nhỏ nhất, nhưng phải công bố cách diễn giải và giới hạn.
- **Trạng thái nghiệp vụ:** mô tả tập giá trị như `pending`, `confirmed`, `cancelled`; tránh bắt client đoán nghĩa của mã số nội bộ.
- **Số lượng:** quy định miền hợp lệ, chẳng hạn `quantity` là số nguyên dương trong request tạo dòng hàng.

Không đổi ID từ chuỗi sang số hoặc đổi tiền từ chuỗi sang JSON number chỉ vì dữ liệu mẫu trông tương đương. Client có thể đã sinh kiểu dữ liệu, validate và lưu giá trị theo hợp đồng cũ.

## 3. Trường vắng mặt, `null` và mảng rỗng

Ba biểu diễn này không tự động mang cùng nghĩa:

```json
{}
```

```json
{
  "deliveryInstructions": null
}
```

```json
{
  "deliveryInstructions": "Gọi trước khi giao"
}
```

Trong response mặc định của ví dụ, `deliveryInstructions` luôn hiện diện; `null` nghĩa là chưa có hướng dẫn giao hàng. Nếu hỗ trợ lựa chọn trường, nó có thể vắng mặt vì client không yêu cầu. Tài liệu phải phân biệt hai trường hợp.

Tính bắt buộc xuất hiện và khả năng nhận `null` là hai câu hỏi độc lập. Một trường có thể bắt buộc xuất hiện nhưng cho phép `null`.

Với collection đã được đưa vào response, dùng mảng rỗng để biểu diễn không có phần tử:

```json
{
  "attachments": []
}
```

Nếu collection chưa được tải hoặc chỉ được biểu diễn bằng liên kết, không dùng `[]` để giả làm dữ liệu đã tải nhưng rỗng. Client có thể hiểu sai rằng không có tệp đính kèm. Trường bị lược bỏ vì quyền truy cập cũng cần quy tắc rõ; tránh vô tình tiết lộ dữ liệu nhạy cảm thông qua sự hiện diện của một trường.

### Ý nghĩa trong cập nhật từng phần

Với JSON Merge Patch và media type `application/merge-patch+json`, thuộc tính bị bỏ qua không được thay đổi; thuộc tính có giá trị `null` yêu cầu loại bỏ thuộc tính khỏi tài liệu đích. API phải kiểm tra thao tác theo quy tắc resource, chẳng hạn từ chối loại bỏ trường bắt buộc. Nếu cần lưu `null` thực sự với một nghĩa riêng, phải chọn cách cập nhật diễn đạt được điều đó.

Nếu dùng DTO cập nhật riêng qua `application/json`, hãy định nghĩa ngữ nghĩa của chính API. Không mặc định mọi request `PATCH` đều theo JSON Merge Patch. Một DTO Java chỉ có trường `String` nhận `null` thường không đủ để phân biệt thuộc tính không được gửi và thuộc tính được gửi rõ là `null`; cơ chế binding cần bảo toàn thông tin về sự hiện diện khi nghiệp vụ cần phân biệt.

## 4. Khi nào nên lồng object?

Lồng object hữu ích khi một nhóm thuộc tính tạo thành khái niệm gắn kết:

```json
{
  "shippingAddress": {
    "recipientName": "Nguyen An",
    "addressLine1": "12 Duong A",
    "locality": "Khu vuc B",
    "countryCode": "VN"
  }
}
```

Trong ví dụ, `shippingAddress` là bản chụp địa chỉ thuộc đơn hàng tại lúc đặt. Khách sửa địa chỉ hồ sơ sau đó không tự sửa địa chỉ của đơn đã xác nhận.

So với các trường phẳng `shippingRecipientName`, `shippingAddressLine1`, `shippingLocality`, object lồng giữ được nhóm ý nghĩa và giúp tránh lặp tiền tố. Tuy vậy, lồng thêm tầng chỉ để tạo cấu trúc có thể làm client khó sử dụng:

```json
{
  "order": {
    "details": {
      "information": {
        "shipping": {
          "address": {
            "addressLine1": "12 Duong A"
          }
        }
      }
    }
  }
}
```

Các tầng `details`, `information` không giải thích thêm khái niệm nghiệp vụ. Nếu representation đã là một đơn, không cần bọc thêm `order`, trừ khi envelope đó có mục đích được quy định, chẳng hạn chứa metadata ngoài resource.

Không có độ sâu tối đa đúng cho mọi API. Hãy xét:

1. Mỗi tầng có đại diện cho khái niệm mà client hiểu không?
2. Object con phụ thuộc vòng đời của cha hay được quản lý độc lập?
3. Payload có tăng mạnh khi quan hệ tăng không?
4. Client có thực sự dùng các tầng dữ liệu sâu không?
5. Cập nhật, phân quyền và cache dữ liệu con có cần tách khỏi cha không?

## 5. Phân biệt giá trị, bản chụp và resource liên quan

Một object nằm trong JSON chưa đủ để kết luận nó là resource độc lập.

| Dạng dữ liệu | Ví dụ | Đặc điểm hợp đồng |
| --- | --- | --- |
| Giá trị thuộc resource | Kích thước kiện hàng | Không nhất thiết có ID hoặc URI riêng |
| Bản chụp nghiệp vụ | Địa chỉ giao hàng đã chốt | Giữ dữ liệu lịch sử theo thời điểm xác định |
| Bản tóm tắt resource khác | Khách trong response đơn | Có định danh riêng; chỉ chứa một phần dữ liệu |
| Resource con | Dòng hàng của đơn | Có thể có ID trong phạm vi đơn và thao tác qua URI con |
| Collection liên quan | Lịch sử thanh toán | Có thể lớn, cần endpoint và phân trang riêng |

Trong hợp đồng minh họa, `customer.displayName` phản ánh tên hiện tại mà người gọi được phép xem khi đọc đơn, không phải tên lịch sử trên hóa đơn. Nếu cần tên lịch sử, dùng trường có nghĩa riêng như `billingCustomerName` và công bố thời điểm chụp dữ liệu.

Tên sản phẩm hiện tại và tên tại thời điểm mua cũng có thể khác nhau. Một trường `name` không được giải thích sẽ khiến client không biết dữ liệu có thể thay đổi sau khi đơn hoàn tất hay không. Hãy mô hình hóa rõ nhu cầu hiển thị hiện tại và nhu cầu giữ lịch sử.

## 6. Ba cách biểu diễn quan hệ

### 6.1. Chỉ đưa ID

```json
{
  "id": "ord_8f2",
  "customerId": "cus_42"
}
```

Cách này gọn và thường thích hợp trong request tạo hoặc thay đổi quan hệ. Client cần tài liệu hoặc quy ước endpoint để lấy khách hàng tương ứng.

Nó phù hợp khi client đã có dữ liệu liên quan hoặc chỉ cần định danh. Đổi lại, màn hình cần tên của nhiều khách có thể phải gọi thêm nhiều request nếu API không có cách lấy dữ liệu phù hợp.

Với quan hệ đa hình có thể trỏ tới nhiều loại resource, ID đơn lẻ có thể chưa đủ. Hợp đồng cần loại resource hoặc liên kết có thể truy cập; không buộc client suy loại từ định dạng ID.

### 6.2. Nhúng bản tóm tắt

```json
{
  "id": "ord_8f2",
  "customer": {
    "id": "cus_42",
    "displayName": "Nguyen An"
  }
}
```

Bản tóm tắt phục vụ hiển thị thường gặp mà không tải toàn bộ hồ sơ. Tài liệu nên định nghĩa một schema như `CustomerSummary`, với tập trường và quy tắc hiện diện rõ ràng.

Tránh để `customer` lúc là chuỗi, lúc là object tùy endpoint hoặc tham số mà không có hợp đồng kiểu hợp rõ ràng. Có thể giữ kiểu object nhất quán, hoặc tách `customerId` và `customer` với mục đích riêng.

Nhúng summary không có nghĩa client được sửa khách hàng bằng cách gửi lại object ấy vào endpoint cập nhật đơn.

### 6.3. Cung cấp liên kết

```json
{
  "id": "ord_8f2",
  "_links": {
    "self": {
      "href": "/orders/ord_8f2"
    },
    "customer": {
      "href": "/customers/cus_42"
    }
  }
}
```

Liên kết chỉ ra nơi truy cập resource liên quan. `_links` ở đây là quy ước của API ví dụ; dùng key này không tự làm API tuân thủ một chuẩn hypermedia cụ thể. Nếu chọn chuẩn có sẵn, phải tuân thủ cấu trúc và media type của chuẩn đó.

Các `href` bắt đầu bằng `/` trong bài là URI-reference được giải quyết theo origin của API. Có thể công bố URI tuyệt đối khi cần, nhưng phải quy định nhất quán cách giải quyết liên kết.

Client nên coi URL là giá trị để sử dụng, không phân tích đường dẫn nhằm suy quan hệ nội bộ. URL không thay thế phân quyền: truy cập `/customers/cus_42` vẫn phải kiểm tra theo người gọi.

### 6.4. Kết hợp có chủ đích

Response có thể vừa nhúng summary để hiển thị, vừa cung cấp liên kết để lấy thêm dữ liệu.

| Nhu cầu | Lựa chọn thường phù hợp | Điều cần mô tả |
| --- | --- | --- |
| Gán khách cho đơn mới | `customerId` trong request | Tồn tại, quyền truy cập và điều kiện được phép gán |
| Hiển thị tên khách trên trang đơn | `customer` dạng summary | Tên hiện tại hay bản chụp |
| Mở chi tiết khách hàng | Liên kết `customer` | Endpoint đích có quyền và hợp đồng riêng |
| Đọc toàn bộ thanh toán | Liên kết collection | Phân trang và giới hạn tải |
| Thể hiện địa chỉ đã chốt | Object bản chụp lồng | Không thay theo địa chỉ hồ sơ |

Không cần công bố đồng thời `customerId`, `customer.id` và nhiều URL chỉ để dự phòng. Nếu có giá trị lặp, phải xác định nguồn chuẩn và bảo đảm nhất quán.

## 7. Collection và các loại quan hệ

### 7.1. Một–nhiều có kích thước được giới hạn

Có thể nhúng dòng hàng nếu số lượng có giới hạn nghiệp vụ hợp lý và client cần nó để đọc đơn:

```json
{
  "id": "ord_8f2",
  "items": [
    {
      "id": "line_1",
      "product": {
        "id": "prd_17",
        "name": "Binh giu nhiet"
      },
      "quantity": 2,
      "unitPriceAmount": "250000"
    }
  ],
  "currency": "VND"
}
```

Giá mỗi đơn vị ở đây dùng cùng `currency` cấp đơn hàng. Nếu cho phép nhiều loại tiền trong một đơn, quy ước này không đủ; tiền tệ phải xuất hiện ở phạm vi phù hợp.

Dòng hàng có `id` ổn định trong phạm vi đơn. Không dùng vị trí mảng làm định danh vì thêm hoặc sắp xếp phần tử sẽ đổi vị trí. Nếu thứ tự có ý nghĩa nghiệp vụ, công bố quy tắc sắp xếp hoặc trường `position` riêng.

### 7.2. Collection lớn hoặc tăng liên tục

Lịch sử sự kiện, bình luận hoặc thanh toán có thể tăng theo thời gian. Nhúng toàn bộ vào mọi response làm tải mạng và chi phí truy vấn khó kiểm soát. Có thể dùng liên kết:

```json
{
  "id": "ord_8f2",
  "_links": {
    "payments": {
      "href": "/orders/ord_8f2/payments"
    }
  }
}
```

Endpoint collection tự quy định phân trang và thứ tự. Nếu có `paymentCount`, cần nói rõ nó đếm phạm vi nào, tại thời điểm nào và có cùng phạm vi quyền với collection hay không.

Một mảng preview vài phần tử không được trình bày như toàn bộ collection. Tên trường và metadata phải cho client biết dữ liệu chưa đầy đủ, đồng thời cung cấp cách đọc tiếp.

### 7.3. Nhiều–nhiều có thuộc tính riêng

Người dùng có thể thuộc nhiều nhóm; mỗi lần tham gia có vai trò và ngày tham gia. Đây không chỉ là mảng `groupIds`:

```json
{
  "id": "mem_91",
  "user": {
    "id": "usr_12"
  },
  "group": {
    "id": "grp_7"
  },
  "role": "editor",
  "joinedAt": "2026-11-01T09:00:00Z"
}
```

Có thể mô hình hóa `membership` thành resource nếu cần định danh, cập nhật vai trò, phân quyền hoặc theo dõi vòng đời riêng. Quyết định dựa trên nghiệp vụ và thao tác của client, không phải sao chép máy móc bảng nối.

### 7.4. Quan hệ tùy chọn

Đơn chưa có người xử lý có thể dùng:

```json
{
  "id": "ord_8f2",
  "assignee": null
}
```

Khi được gán, `assignee` là object summary. Tài liệu phải nói `null` nghĩa là chưa gán, thay vì chưa tải hoặc không có quyền xem. Nếu các trạng thái đó cần cách xử lý khác nhau, không gom tất cả vào cùng một giá trị mơ hồ.

## 8. Một response hoàn chỉnh

Biểu diễn mặc định của đơn hàng trong API ví dụ:

```json
{
  "id": "ord_8f2",
  "status": "confirmed",
  "customer": {
    "id": "cus_42",
    "displayName": "Nguyen An"
  },
  "shippingAddress": {
    "recipientName": "Nguyen An",
    "addressLine1": "12 Duong A",
    "locality": "Khu vuc B",
    "countryCode": "VN"
  },
  "deliveryInstructions": null,
  "items": [
    {
      "id": "line_1",
      "product": {
        "id": "prd_17",
        "name": "Binh giu nhiet"
      },
      "quantity": 2,
      "unitPriceAmount": "250000"
    }
  ],
  "totalAmount": "500000",
  "currency": "VND",
  "createdAt": "2026-11-17T08:30:00Z",
  "_links": {
    "self": {
      "href": "/orders/ord_8f2"
    },
    "customer": {
      "href": "/customers/cus_42"
    },
    "payments": {
      "href": "/orders/ord_8f2/payments"
    }
  }
}
```

JSON đơn lẻ chưa mô tả hết hợp đồng. Cần công bố thêm:

- `customer`, `product` là summary của resource độc lập, không phải toàn bộ hồ sơ.
- `shippingAddress` là bản chụp lưu cùng đơn; thay đổi hồ sơ không cập nhật ngược bản chụp.
- `items` là collection đầy đủ theo giới hạn số dòng hàng của API; ID dòng hàng chỉ cần duy nhất trong phạm vi đơn tương ứng.
- `unitPriceAmount` là giá đã chốt; `product.name` trong ví dụ là tên hiện tại. Nhu cầu tên lịch sử cần trường bản chụp riêng.
- `deliveryInstructions` bắt buộc hiện diện trong biểu diễn mặc định nhưng cho phép `null`.
- `totalAmount` do server tính. Ví dụ chưa có phí và giảm giá nên tổng bằng hai lần đơn giá.
- Các trường tiền là chuỗi thập phân theo cùng `currency`, không phải số dấu phẩy động JSON.
- Liên kết khách phải trỏ tới đúng ID trong summary; thanh toán được đọc qua collection riêng.

Đưa tên trường, kiểu, trường bắt buộc, khả năng nhận `null`, giới hạn mảng và các schema như `CustomerSummary` vào OpenAPI hoặc tài liệu tương đương. Ý nghĩa bản chụp, thời điểm đọc và cách tính tổng cần mô tả bằng lời. Chỉ khai báo kiểu `object` chưa đủ để tạo hợp đồng rõ ràng.

## 9. Request và response có trách nhiệm khác nhau

Response trên không phải mẫu để client gửi ngược toàn bộ khi tạo đơn. Request có thể chỉ gồm:

```http
POST /orders
Content-Type: application/json
```

```json
{
  "customerId": "cus_42",
  "shippingAddress": {
    "recipientName": "Nguyen An",
    "addressLine1": "12 Duong A",
    "locality": "Khu vuc B",
    "countryCode": "VN"
  },
  "items": [
    {
      "productId": "prd_17",
      "quantity": 2
    }
  ]
}
```

`customerId`, `productId` là tham chiếu client đề nghị sử dụng. Server kiểm tra tồn tại, quyền truy cập, trạng thái sử dụng và ràng buộc nghiệp vụ; không chỉ kiểm tra kiểu chuỗi.

Trong thao tác này, server quyết định `id`, `createdAt`, giá đã chốt và `totalAmount`. API cần chính sách rõ với trường input ngoài hợp đồng: từ chối hoặc xử lý theo quy tắc đã công bố. DTO input riêng giúp tránh vô tình cho phép client sửa thuộc tính nội bộ.

Không coi object lồng là chỉ thị cập nhật lan truyền. Nếu endpoint đơn nhận `customer.displayName`, client cần biết nó có đổi tên khách hay không. Cách dễ kiểm soát là endpoint đơn chỉ nhận giá trị thuộc đơn và tham chiếu được phép thay đổi; sửa hồ sơ khách qua thao tác riêng, với kiểm tra quyền riêng.

Ý nghĩa cập nhật collection cũng cần rõ. Một mảng `items` có thể mang nghĩa thay toàn bộ, thêm mới hoặc sửa phần tử theo ID. Hình dạng JSON không tự xác định hành vi và tính idempotency. Hợp đồng phải nói cách xác định phần tử, phạm vi thay thế và cách xử lý phần tử bị bỏ qua.

## 10. Ánh xạ DTO trong Java/Spring

Không nên trả trực tiếp entity ORM có đồ thị `Order → Customer → Orders → Customer ...`. Serialize theo đồ thị có thể gây vòng lặp, truy vấn ngoài dự kiến hoặc lộ trường ngoài hợp đồng. Annotation ngăn vòng lặp không tự thiết kế ranh giới API.

Ví dụ sau dùng Java record và Jackson để mô tả response, không phải entity:

```java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.OffsetDateTime;
import java.util.List;

record CustomerSummary(String id, String displayName) {}
record ProductSummary(String id, String name) {}

record ShippingAddressResponse(
    String recipientName,
    String addressLine1,
    String locality,
    String countryCode
) {}

record OrderItemResponse(
    String id,
    ProductSummary product,
    int quantity,
    String unitPriceAmount
) {}

record LinkResponse(String href) {}

record OrderLinks(
    LinkResponse self,
    LinkResponse customer,
    LinkResponse payments
) {}

@JsonInclude(JsonInclude.Include.ALWAYS)
record OrderResponse(
    String id,
    String status,
    CustomerSummary customer,
    ShippingAddressResponse shippingAddress,
    String deliveryInstructions,
    List<OrderItemResponse> items,
    String totalAmount,
    String currency,
    OffsetDateTime createdAt,
    @JsonProperty("_links") OrderLinks links
) {}
```

Các điểm cần giữ khi triển khai:

1. Lớp application hoặc mapper dựng DTO từ dữ liệu phù hợp sau kiểm tra quyền. Serializer không tự đi theo mọi quan hệ ORM.
2. `@JsonProperty("_links")` ánh xạ tên Java `links` sang key công khai.
3. Cấu hình serialize thời gian phải xuất chuỗi đã cam kết. Chỉ chọn `OffsetDateTime` chưa bảo đảm hình dạng JSON khi cấu hình mapper thay đổi.
4. Annotation include thể hiện chủ đích giữ `deliveryInstructions` ngay cả khi `null`; kiểm thử JSON thực tế vẫn cần khi có cấu hình hoặc serializer tùy biến.
5. Dựng trường tiền từ kiểu thập phân chính xác như `BigDecimal`, theo quy tắc scale rõ ràng, rồi xuất chuỗi theo hợp đồng; tránh tính tiền bằng `double`.
6. `items` là danh sách đã tải trong phạm vi cho phép; không trả `null` khi hợp đồng yêu cầu mảng.

Request tạo đơn cần các DTO khác như `CreateOrderRequest`, `CreateOrderItemRequest`. Chúng không có trường do server quản lý chỉ vì response có trường đó. Validation input và kiểm tra quyền quan hệ phải diễn ra trước khi ghi dữ liệu.

## 11. Mở rộng quan hệ và độ mới của biểu diễn

Một số API hỗ trợ mở rộng có giới hạn:

```http
GET /orders/ord_8f2?expand=items.product
```

`expand` là tham số riêng của API ví dụ, không phải cú pháp mặc định của REST. Nếu hỗ trợ, cần công bố:

- Các đường dẫn hợp lệ và phản hồi lỗi khi giá trị không được hỗ trợ.
- Độ sâu, số phần tử và chi phí tối đa.
- Những trường được thêm và kiểu dữ liệu có giữ ổn định không.
- Quyền cần có với resource và trường được mở rộng.
- Hành vi khi dữ liệu liên quan bị xóa hoặc không còn được phép truy cập.

Có thể giữ `product` dạng summary và bổ sung `productDetails` theo schema riêng, hoặc giữ cấu trúc object nền tảng rồi thêm các trường đã mô tả. Tránh tự đổi `product` từ chuỗi sang object chỉ vì thêm tham số nếu điều đó làm client phải xử lý kiểu bất ngờ.

Nếu response đơn chứa tên hiện tại của khách, tên khách đổi có thể làm biểu diễn đơn đổi dù bản ghi đơn không đổi. ETag hoặc cơ chế xác định độ mới phải xét dữ liệu thực sự có trong biểu diễn. Nếu chỉ xét thời điểm sửa đơn, server có thể xác nhận cache còn mới trong khi phần dữ liệu nhúng đã thay đổi.

Cache ứng dụng cũng cần phân biệt lựa chọn biểu diễn như `expand`, lựa chọn trường và phạm vi người dùng nếu nội dung phụ thuộc quyền. Đây là hệ quả của hợp đồng dữ liệu, không chỉ là tối ưu truy vấn.

## 12. Thay đổi hợp đồng và khả năng tương thích

| Thay đổi | Rủi ro với client | Hướng xử lý |
| --- | --- | --- |
| `customerId` thành `customer.id` | Đường dẫn truy cập thay đổi | Giữ hợp đồng cũ trong giai đoạn chuyển tiếp hoặc phát hành hợp đồng mới |
| `items: []` thành `items: null` | Code lặp mảng có thể lỗi | Giữ quy tắc mảng đã công bố |
| ID chuỗi thành số | Sai kiểu hoặc mất chính xác | Giữ kiểu ID công khai ổn định |
| Tiền chuỗi thành JSON number | Bộ giải mã và cách tính thay đổi | Dùng trường hoặc phiên bản hợp đồng mới khi cần |
| Bản chụp thành dữ liệu hiện tại | Lịch sử thay đổi ý nghĩa | Dùng trường có tên và mô tả riêng |
| Bắt buộc input trước đây tùy chọn | Request cũ bị từ chối | Giá trị mặc định hợp lý hoặc kế hoạch chuyển đổi |

Thêm trường response thường dễ tương thích nếu client bỏ qua trường chưa biết, nhưng client dùng schema đóng hoặc bộ giải mã nghiêm ngặt vẫn có thể lỗi. Thêm giá trị enum cũng có thể phá vỡ client dùng tập giá trị đóng.

Quy định cách xử lý trường và giá trị chưa biết, đồng thời kiểm thử với client thực tế. Giữ nguyên URI không bảo đảm tương thích nếu cấu trúc hoặc nghĩa dữ liệu đã đổi.

## 13. Lỗi thường gặp và cách sửa

### Trả thẳng entity rồi sửa dần bằng annotation

Dấu hiệu: thêm quan hệ ORM làm response tự xuất hiện object mới; đổi tên property Java làm key JSON đổi. Hãy xác định schema công khai, tạo DTO và ánh xạ tường minh. Annotation phục vụ hợp đồng đã chọn.

### Nhúng hai chiều không có điểm dừng

Dấu hiệu: `order.customer.orders[0].customer...` hoặc payload tăng mạnh theo dữ liệu thật. Chọn một hướng nhúng có giới hạn; dùng summary hoặc liên kết cho chiều còn lại. Danh sách đơn của khách cần collection với phạm vi và phân trang rõ.

### Một trường có nhiều hình dạng không được mô tả

Dấu hiệu: `customer` khi là chuỗi, khi là object hoặc mảng. Giữ kiểu ổn định. Nếu miền thực sự cần kiểu hợp, mô tả các biến thể và dấu phân loại trong schema; không tạo nhiều hình dạng chỉ vì tiện serialize.

### Preview bị hiểu là toàn bộ collection

Dấu hiệu: response có năm bình luận mà không cho biết còn dữ liệu khác. Công bố tính đầy đủ, metadata phân trang hoặc liên kết đọc tiếp; không khiến client hiểu thiếu dữ liệu thành không có dữ liệu.

### Nhận toàn bộ object lồng để cập nhật

Dấu hiệu: client không biết sửa tên khách trong JSON đơn có đổi hồ sơ khách không. Định nghĩa DTO theo thao tác; phân biệt thay quan hệ, sửa giá trị thuộc đơn và cập nhật resource độc lập, với quyền và quy tắc tương ứng.

## 14. Bài thực hành

Thiết kế `/projects/{projectId}` với các yêu cầu:

- Dự án có tên, chủ sở hữu và ngày tạo.
- Dự án sở hữu cấu hình giới hạn lưu trữ.
- Thành viên có vai trò, ngày tham gia; collection có thể rất lớn.
- Trang tổng quan chỉ cần tên chủ và số thành viên người gọi được phép xem.
- Có thể chuyển chủ nếu đủ quyền, nhưng không sửa hồ sơ người mới qua request dự án.

Thực hiện:

1. Viết response mặc định; phân loại object giá trị, summary và quan hệ độc lập.
2. Chọn cách biểu diễn thành viên và giải thích quyết định nhúng hoặc dùng liên kết.
3. Viết request chuyển chủ; xác định trường không được cập nhật và kiểm tra quan hệ cần thực hiện.
4. Định nghĩa quan hệ chủ sở hữu không tồn tại nếu nghiệp vụ cho phép trạng thái đó.
5. Nêu một thay đổi tương thích và một thay đổi cần kế hoạch chuyển đổi client.

Một hướng là `owner` dạng summary, `storagePolicy` dạng object giá trị, `visibleMemberCount` có phạm vi quyền rõ và liên kết tới `/projects/{projectId}/memberships`. Request chuyển chủ nhận `ownerId`; server kiểm tra quyền, tính hợp lệ của người mới và quy tắc chuyển giao. Nếu nghiệp vụ bắt buộc có chủ, không thêm trạng thái `null` chỉ để làm JSON linh hoạt hơn.

## 15. Tự kiểm tra thiết kế

Trước khi bàn giao schema, đối chiếu:

- Tên, kiểu, đơn vị và nghĩa nghiệp vụ có nhất quán không?
- Tính bắt buộc xuất hiện và khả năng nhận `null` đã tách riêng chưa?
- Collection là đầy đủ, preview hay một trang; client phân biệt bằng gì?
- Object lồng là giá trị, bản chụp, summary hay resource độc lập?
- Thời điểm chụp và thời điểm đọc dữ liệu hiện tại có rõ không?
- Cấu trúc có tránh vòng lặp và payload tăng không giới hạn không?
- Client có đường đọc dữ liệu liên quan khi summary chưa đủ không?
- Request có giới hạn đúng thao tác và trường được ghi không?
- Quyền có được kiểm tra với cả resource chính, quan hệ và trường nhúng không?
- Dữ liệu liên quan thay đổi có ảnh hưởng đến độ mới và cache không?

Khi triển khai, các kiểm thử hợp đồng hữu ích gồm: kiểm tra key và kiểu JSON thực tế; trường nullable vẫn hiện diện khi bắt buộc; collection rỗng vẫn là mảng; summary không lộ trường nhạy cảm; liên kết và ID trỏ cùng resource; request không sửa được trường server quản lý; kiểu quan hệ giữ ổn định khi bật mở rộng.

Quy ước tên tạo tính nhất quán, ranh giới lồng tạo ý nghĩa, còn cách biểu diễn quan hệ xác định client đọc và thao tác với dữ liệu liên quan như thế nào. Những quyết định này cần xuất hiện trong hợp đồng và ví dụ, thay vì buộc client suy đoán từ dữ liệu tình cờ nhận được.
