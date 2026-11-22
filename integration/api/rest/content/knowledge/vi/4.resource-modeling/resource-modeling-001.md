# Nhận diện tài nguyên từ khái niệm nghiệp vụ

## Mục tiêu bài học

Trong chương **Mô hình tài nguyên** của module **INTEGRATION_API_REST**, bài học này hướng dẫn cách đi từ yêu cầu nghiệp vụ đến một mô hình resource có ý nghĩa đối với người sử dụng API.

Sau bài học, bạn cần:

- Tìm được các ứng viên tài nguyên từ những tình huống sử dụng cụ thể.
- Phân biệt tài nguyên với bảng dữ liệu, thuộc tính, quan hệ và thao tác.
- Xác định định danh, vòng đời, quyền truy cập và ranh giới của một tài nguyên.
- Chọn cách biểu diễn dữ liệu mà không làm client phụ thuộc vào cấu trúc lưu trữ.
- Ánh xạ mô hình ban đầu sang URI và tương tác HTTP ở mức đủ để kiểm chứng thiết kế.
- Nhận ra phần nghiệp vụ vẫn phải được bảo vệ ở server khi triển khai bằng Java/Spring hoặc công nghệ tương đương.

Ví dụ xuyên suốt là một hệ thống bán hàng có sản phẩm, giỏ hàng, đơn hàng và thanh toán. Mục tiêu không phải thiết kế toàn bộ hệ thống thương mại điện tử, mà là thực hành cách đưa ra và giải thích quyết định về tài nguyên.

## 1. Tài nguyên bắt đầu từ ý nghĩa, không bắt đầu từ đường dẫn

Trong REST, **resource** là một khái niệm được nhận diện và có thể được tương tác thông qua representation. Nó có thể là một đối tượng nghiệp vụ, một tập hợp, một kết quả tính toán hoặc một công việc cần theo dõi.

Ví dụ:

- Một sản phẩm cụ thể.
- Một đơn hàng cụ thể.
- Tập đơn hàng mà một người dùng được phép xem.
- Tình trạng còn hàng của một sản phẩm tại một kho.
- Một công việc xuất báo cáo đang xử lý.

Resource không bắt buộc phải là vật thể có thật, cũng không bắt buộc tương ứng với một dòng trong cơ sở dữ liệu.

Với một đơn hàng:

~~~text
Khái niệm nghiệp vụ: đơn hàng đã được hệ thống ghi nhận
Định danh công khai: ord_204
URI minh họa: /orders/ord_204
Representation: dữ liệu mà API cho phép người gọi xem
Lưu trữ: có thể gồm nhiều bảng hoặc nhiều cấu trúc nội bộ
~~~

Không nên bắt đầu bằng câu hỏi “đặt URL này là gì?”. Hãy làm rõ đối tượng nào tồn tại trong nghiệp vụ, người dùng cần làm gì với nó và những quy tắc nào phải giữ đúng.

### 2.1. Phân biệt identity, state và representation

| Khái niệm | Câu hỏi | Ví dụ với đơn hàng |
|---|---|---|
| Identity | Đây là đối tượng nào, có phải đối tượng đã được nói đến trước đó không? | Đơn hàng `ord_204` |
| State | Hiện tại đối tượng đang có những giá trị và điều kiện nào? | Chờ thanh toán, tổng tiền 250.000 VND |
| Representation | Người gọi được trao đổi dữ liệu mô tả đối tượng dưới dạng nào? | JSON chứa ID, trạng thái, các dòng hàng và tổng tiền |

Đơn hàng vẫn là đơn hàng đó khi chuyển từ chờ thanh toán sang đã xác nhận. Không cần cấp một định danh mới chỉ vì trạng thái thay đổi.

Ngược lại, hai đơn hàng có cùng sản phẩm và cùng tổng tiền vẫn có thể là hai đối tượng khác nhau.

Một resource cũng có thể có nhiều representation: bản tóm tắt cho danh sách, bản chi tiết cho người mua hoặc một biểu diễn theo media type khác. Representation không phải bản sao bắt buộc của mọi dữ liệu lưu ở server.

## 3. Bắt đầu từ tình huống sử dụng

Giả sử yêu cầu ban đầu là:

> Người mua xem sản phẩm, thêm hàng vào giỏ, thay đổi số lượng và đặt hàng. Khi đặt hàng, hệ thống xác lập giá tại thời điểm đặt, ghi nhận thông tin giao hàng và tổng tiền. Người mua có thể theo dõi đơn của mình. Hệ thống theo dõi từng lần thanh toán và chỉ cho phép hủy đơn khi thỏa điều kiện nghiệp vụ.

Đừng lập tức tạo endpoint cho từng động từ. Trước tiên, hãy tách yêu cầu thành các tình huống và câu hỏi.

| Tình huống | Điều cần hiểu |
|---|---|
| Xem sản phẩm | Client cần mô tả sản phẩm, giá hay tình trạng tồn kho nào? |
| Thêm vào giỏ | Giỏ có định danh và tồn tại qua nhiều request không? |
| Thay đổi số lượng | Dòng giỏ hàng được nhận diện ra sao, số lượng hợp lệ thế nào? |
| Đặt hàng | Khi nào đơn được coi là đã tồn tại, dữ liệu nào được chốt? |
| Theo dõi đơn | Người gọi có quyền xem đơn nào, trạng thái nào cần công bố? |
| Thanh toán | Có thể có nhiều lần thử cho một đơn không, cần tra cứu từng lần không? |
| Hủy đơn | Đây là chuyển trạng thái đơn hay một yêu cầu có quy trình và lịch sử riêng? |

Những câu trả lời có thể làm thay đổi mô hình. Ví dụ, nếu hệ thống cần đối soát nhiều lần thanh toán cho cùng một đơn, “thanh toán” khó được biểu diễn đầy đủ bằng một trường boolean `paid`.

### 3.1. Danh từ là ứng viên, không phải kết luận

Từ yêu cầu có thể tìm được các danh từ:

~~~text
người mua
sản phẩm
giỏ hàng
dòng giỏ hàng
số lượng
đơn hàng
giá
địa chỉ
tổng tiền
thanh toán
yêu cầu hủy
~~~

Không phải mỗi danh từ phải trở thành một endpoint riêng.

- Số lượng thường là thuộc tính của dòng hàng.
- Tổng tiền thường là giá trị được tính theo hợp đồng.
- Địa chỉ có thể là giá trị được chụp lại trong đơn.
- Thanh toán có thể là resource riêng nếu có định danh và vòng đời cần theo dõi.

Danh sách này là đầu vào cho phân tích, không phải danh sách controller phải tạo.

### 3.2. Động từ giúp tìm ra trách nhiệm và chuyển trạng thái

Các động từ như “đặt”, “xác nhận”, “thanh toán”, “hủy” giúp bạn hỏi:

- Đối tượng nào thay đổi?
- Kết quả nào cần được nhận diện?
- Có điều kiện trước khi thực hiện không?
- Có tác động phụ sang hệ thống khác không?
- Client có cần theo dõi tiến trình hoặc lịch sử không?

Ví dụ, “đặt hàng” có thể tạo một resource đơn hàng. “Xuất báo cáo” có thể tạo một công việc xuất nếu cần theo dõi kết quả về sau.

Đổi tên `cancelOrder` thành danh từ `cancellation` mà chưa làm rõ những câu hỏi trên chưa phải là mô hình hóa đầy đủ.

## 4. Bộ câu hỏi để đánh giá một ứng viên tài nguyên

Với mỗi ứng viên, hãy hỏi:

1. **Ý nghĩa:** người dùng hoặc hệ thống đang nói đến điều gì?
2. **Định danh:** có cần phân biệt nó với những đối tượng cùng loại không?
3. **Vòng đời:** nó được tạo, thay đổi và kết thúc như thế nào?
4. **Tương tác:** có nhu cầu đọc, tạo hoặc tác động tới nó không?
5. **Quyền:** ai có thể xem hoặc thực hiện từng thao tác?
6. **Quan hệ:** nó liên hệ với đối tượng nào và phụ thuộc vào ai?
7. **Bất biến nghiệp vụ:** điều gì phải luôn đúng?
8. **Biểu diễn:** client cần nhận và gửi những dữ liệu nào?

Đây không phải bài chấm điểm bắt buộc một ứng viên phải đạt đủ tám ô mới được gọi là resource. Chẳng hạn, một tập kết quả tính toán có thể không có vòng đời được lưu như một đơn hàng.

Bộ câu hỏi giúp phát hiện những quyết định còn thiếu.

### Ví dụ: đơn hàng

~~~text
Ý nghĩa:
  Cam kết mua hàng mà hệ thống đã ghi nhận.

Định danh:
  Một ID công khai ổn định, ví dụ ord_204.

Vòng đời minh họa:
  PENDING_PAYMENT → CONFIRMED → COMPLETED
  PENDING_PAYMENT → CANCELLED

Tương tác:
  Tạo từ giỏ hàng; đọc chi tiết; yêu cầu hủy khi được phép.

Quyền:
  Người mua được xem đơn thuộc phạm vi của mình.
  Nhân viên được thực hiện những thao tác theo quyền được cấp.

Bất biến:
  Số lượng dòng hàng phải dương.
  Tổng tiền được tính theo quy tắc của hệ thống.
  Không xác nhận đơn bằng cách nhận tùy ý một chuỗi status từ client.
~~~

Vòng đời trên chỉ là hợp đồng giả định cho ví dụ. Một sản phẩm thực tế có thể cần thêm trạng thái hoặc điều kiện khác.

## 5. Phân biệt tài nguyên, giá trị, quan hệ và thao tác

### 5.1. Giá trị không nhất thiết có định danh riêng

Một số tiền có thể được biểu diễn:

~~~json
{
  "amount": 250000,
  "currency": "VND"
}
~~~

Trong ví dụ, hợp đồng quy định `amount` là số tiền nguyên theo đơn vị VND. Những loại tiền, phép tính và cách làm tròn khác cần được định nghĩa riêng.

Nếu client chỉ cần biết tổng tiền của đơn, không có lý do mặc định phải tạo:

~~~text
/money-values/887
~~~

Số tiền ở đây là một giá trị của đơn hàng, không phải một đối tượng có vòng đời độc lập cần công bố.

Tương tự, tên hiển thị, số lượng và một địa chỉ snapshot có thể là các giá trị trong representation.

### 5.2. Cùng một khái niệm có thể được mô hình khác nhau theo nhu cầu

Địa chỉ giao hàng trong sổ địa chỉ của người mua có thể là một resource có ID để cập nhật và lựa chọn.

Địa chỉ đã ghi vào đơn hàng thường cần giữ lại ý nghĩa lịch sử tại thời điểm đặt. Nếu người mua sửa sổ địa chỉ, đơn cũ không nên tự chuyển sang địa chỉ mới trừ khi nghiệp vụ chủ đích cho phép.

Có thể tồn tại đồng thời:

- Resource địa chỉ trong sổ địa chỉ.
- Giá trị snapshot địa chỉ trong đơn hàng.

Tương tự:

- Giá hiện tại của sản phẩm có thể là thuộc tính.
- Một bảng giá có hiệu lực theo thời gian có thể là resource.
- Một báo giá có mã, thời hạn và bước chấp nhận có thể là resource riêng.

Quyết định đến từ nhu cầu nhận diện và tương tác, không phải từ tên gọi của dữ liệu.

### 5.3. Quan hệ không tự động là một resource mới

Ví dụ, một đơn hàng liên quan đến người mua:

~~~json
{
  "id": "ord_204",
  "customerId": "cus_15"
}
~~~

API có thể biểu diễn quan hệ bằng ID, link hoặc dữ liệu nhúng theo hợp đồng.

Không nhất thiết tạo một endpoint riêng cho mọi khóa ngoại. Nhưng nếu quan hệ có thuộc tính và vòng đời riêng, nó có thể đáng được mô hình hóa rõ hơn.

Chẳng hạn, “thành viên của một nhóm” có thể mang vai trò, ngày tham gia và trạng thái. Khi cần quản lý những thông tin đó, membership có thể là resource thay vì chỉ là một cặp ID.

### 5.4. Thao tác nghiệp vụ không bắt buộc tạo một dòng dữ liệu mới

REST không bắt buộc biến mọi động từ thành một bảng hoặc lưu vĩnh viễn mọi yêu cầu.

Nếu yêu cầu hủy chỉ là một chuyển trạng thái đơn, thiết kế có thể thực hiện nó theo một hợp đồng phù hợp với resource đơn.

Nếu yêu cầu hủy cần lý do, xét duyệt, người xử lý và trạng thái riêng, một resource cancellation có thể biểu đạt bài toán tốt hơn.

Điều quan trọng là server có một cách xử lý rõ ràng và giữ đúng ngữ nghĩa HTTP, chứ không phải số lượng danh từ trong URL.

## 6. Từ ứng viên đến mô hình ban đầu

Với phạm vi bán hàng đã nêu, một lựa chọn ban đầu có thể là:

| Khái niệm | Quyết định mô hình | Lý do |
|---|---|---|
| Sản phẩm | Resource | Có định danh và thông tin để tra cứu độc lập |
| Giỏ hàng | Resource | Cần giữ nội dung qua nhiều request và có vòng đời |
| Dòng giỏ hàng | Thành phần có thể có URI con | Cần nhận diện dòng cụ thể để thay đổi số lượng hoặc bỏ khỏi giỏ |
| Số lượng | Thuộc tính | Là giá trị của dòng hàng, không cần vòng đời độc lập |
| Đơn hàng | Resource | Có định danh, trạng thái, quyền và lịch sử nghiệp vụ |
| Dòng đơn hàng | Thành phần của đơn trong thiết kế ban đầu | Cần giữ snapshot; chưa có nhu cầu thao tác độc lập |
| Tổng tiền | Giá trị được tính | Không nhận tùy ý từ client làm kết quả cuối cùng |
| Thanh toán | Resource riêng | Có thể có nhiều lần thử, trạng thái và nhu cầu đối soát |
| Yêu cầu hủy | Chưa tách mặc định | Chỉ tách khi có nhu cầu theo dõi và quản lý riêng |
| Tồn kho | Khái niệm cần phân tích theo phạm vi | Không đồng nhất với sản phẩm; có thể phụ thuộc kho và biến thể |

Đây là mô hình có chủ đích cho ví dụ, không phải công thức bắt buộc cho mọi hệ thống.

### 6.1. Sản phẩm và tồn kho không phải cùng một thứ

Một sản phẩm có thể vẫn tồn tại trong catalog dù hiện không còn hàng.

Cùng một sản phẩm có thể có:

- Nhiều biến thể.
- Số lượng khác nhau theo kho.
- Phần tồn đã được giữ cho các đơn đang xử lý.
- Chính sách đặt trước hoặc giới hạn bán.

Nếu gộp mọi điều này vào một boolean `available` mà không định nghĩa, client khó hiểu `true` thực sự cam kết điều gì.

Bạn có thể cung cấp một biểu diễn availability phù hợp cho người mua, đồng thời giữ mô hình tồn kho chi tiết cho phạm vi quản trị. Không bắt buộc công khai mọi resource nội bộ ra API bên ngoài.

### 6.2. Giỏ hàng và đơn hàng có vòng đời khác nhau

Giỏ hàng phản ánh ý định đang thay đổi. Giá hoặc khả năng cung cấp có thể được kiểm tra lại trước khi đặt.

Đơn hàng phản ánh những thông tin được hệ thống xác lập tại một thời điểm theo hợp đồng. Nó thường cần lưu giá, tên hàng và thông tin giao hàng phục vụ lịch sử.

Nếu chỉ đổi tên “giỏ hàng đã mua” thành đơn nhưng vẫn tham chiếu toàn bộ dữ liệu hiện tại, việc sửa catalog có thể vô tình làm thay đổi lịch sử đơn.

Mô hình tài nguyên cần chỉ ra điểm chuyển từ dữ liệu đang lựa chọn sang dữ liệu đã được ghi nhận.

## 7. Định danh ổn định và phạm vi nhận diện

### 7.1. Phân biệt ID công khai với vị trí lưu trữ

Một ID công khai có thể là số, UUID hoặc chuỗi theo quy ước. Không có yêu cầu rằng nó phải trùng khóa chính cơ sở dữ liệu.

Điều cần xác định:

- ID có ổn định trong vòng đời resource không?
- Có duy nhất trong phạm vi cần thiết không?
- Có thể dùng để tham chiếu lâu dài theo hợp đồng không?
- Client có được phép suy luận cấu trúc bên trong ID không?
- Khi resource hết hạn hoặc bị xóa, request sẽ được xử lý thế nào?

Không cần tạo một cơ chế ID phức tạp chỉ để che cách lưu trữ. Nhưng cũng không nên vô tình biến chi tiết có thể thay đổi thành hợp đồng vĩnh viễn.

### 7.2. Tên, slug và mã hiển thị có thể có vai trò khác

Ví dụ một sản phẩm:

~~~json
{
  "id": "prd_7",
  "slug": "binh-giu-nhiet-500ml",
  "displayName": "Bình giữ nhiệt 500 ml"
}
~~~

Tên hoặc slug có thể thay đổi khi nội dung được cập nhật. Nếu chúng được dùng làm định danh trong URI, API cần chính sách tương ứng về đổi tên và tham chiếu cũ.

Một đơn hàng cũng có thể có ID kỹ thuật công khai và mã hiển thị cho nhân viên. Không nên mặc định hai giá trị này luôn là cùng một thứ.

### 7.3. Tài nguyên con có thể có định danh trong phạm vi cha

Một dòng giỏ hàng có thể được nhận diện bằng:

~~~text
/carts/cart_91/items/line_1
~~~

`line_1` có thể chỉ duy nhất trong giỏ `cart_91`. Không nhất thiết cấp một ID toàn cục nếu nghiệp vụ không cần.

Khi truy cập, server vẫn phải xác nhận dòng thực sự thuộc giỏ được chỉ định và người gọi có quyền trên giỏ đó.

### 7.4. ID không thay thế phân quyền

Biết một URI không có nghĩa người gọi được phép đọc resource.

ID khó đoán có thể giảm khả năng dò tìm, nhưng không thay thế việc kiểm tra quyền sở hữu, phạm vi tổ chức hoặc quyền nghiệp vụ.

Tương tự, không nhận `customerId` do client gửi rồi mặc định tạo đơn cho bất kỳ khách hàng nào. Phải xác định actor và kiểm tra quyền của actor trong tình huống tương ứng.

## 8. Ranh giới tài nguyên và quan hệ sở hữu

Một câu hỏi quan trọng là: thành phần nào có thể được quản lý độc lập và thành phần nào phải được giữ nhất quán cùng đối tượng cha?

Ví dụ:

~~~text
Giỏ hàng
  └── Các dòng giỏ hàng

Đơn hàng
  ├── Các dòng hàng snapshot
  ├── Thông tin giao hàng snapshot
  └── Tổng tiền được xác lập

Thanh toán
  └── Tham chiếu đơn hàng
~~~

Trong mô hình này:

- Dòng giỏ hàng phụ thuộc giỏ.
- Dòng đơn hàng không cần được sửa tùy ý sau khi đơn đã xác lập.
- Thanh toán có thể cần được tra cứu và đối soát riêng.
- Đơn có thể liên quan nhiều lần thanh toán, không chỉ một cờ `paid`.

### 8.1. Ranh giới biểu diễn khác với ranh giới transaction

Một response có thể nhúng thông tin từ nhiều nguồn để client dùng thuận tiện. Điều đó không tự tạo một transaction nguyên tử trên tất cả nguồn.

Ngược lại, một thao tác tạo đơn có thể cần ghi nhiều bảng trong một transaction dù API chỉ tạo một resource công khai.

Không nên suy rằng:

~~~text
1 resource = 1 bảng = 1 entity Java = 1 transaction = 1 service
~~~

Những ranh giới này phục vụ các mục tiêu khác nhau và cần được thiết kế riêng.

### 8.2. Tránh nesting chỉ để phản ánh mọi quan hệ

Một đường dẫn rất sâu như:

~~~text
/customers/cus_15/carts/cart_91/orders/ord_204/payments/pay_81
~~~

có thể làm client phụ thuộc vào một chuỗi quan hệ không cần thiết.

Nếu đơn hàng và thanh toán có định danh phù hợp để truy cập độc lập, có thể cân nhắc:

~~~text
/orders/ord_204
/payments/pay_81
~~~

Quan hệ vẫn được thể hiện trong representation hoặc các điểm truy cập tập hợp có liên quan.

Ngược lại, URI con như `/carts/cart_91/items/line_1` có thể làm rõ phạm vi của một thành phần phụ thuộc. Không có một quy tắc rằng mọi URI con đều sai hoặc mọi resource đều phải nằm ở gốc.

## 9. Chọn representation theo hợp đồng, không theo entity lưu trữ

Giả sử client tạo đơn từ một giỏ có sẵn:

~~~http
POST /orders HTTP/1.1
Host: api.example.com
Content-Type: application/json
Accept: application/json

{
  "cartId": "cart_91"
}
~~~

Server lấy thông tin người gọi từ cơ chế xác thực phù hợp, kiểm tra quyền đối với giỏ, kiểm tra dữ liệu và tính toán theo nghiệp vụ.

Response có thể là:

~~~http
HTTP/1.1 201 Created
Location: /orders/ord_204
Content-Type: application/json

{
  "id": "ord_204",
  "status": "PENDING_PAYMENT",
  "items": [
    {
      "productId": "prd_7",
      "productName": "Bình giữ nhiệt",
      "quantity": 2,
      "unitPrice": {
        "amount": 125000,
        "currency": "VND"
      }
    }
  ],
  "total": {
    "amount": 250000,
    "currency": "VND"
  }
}
~~~

Ví dụ bỏ qua thuế, phí và giảm giá để tập trung vào mô hình.

Các quyết định quan trọng:

- Client gửi ý định tạo từ giỏ, không tự xác lập tổng tiền cuối cùng.
- Trạng thái ban đầu do server quyết định theo hợp đồng.
- Dòng đơn giữ tên và giá đã được xác lập, đồng thời có thể tham chiếu sản phẩm gốc.
- Body request không phải bản sao của body response.
- Những trường nội bộ không cần cho client được giữ ngoài hợp đồng.

### 9.1. Không để client sửa mọi field nhìn thấy

Một field xuất hiện trong response không có nghĩa client được phép ghi field đó.

Ví dụ, cho phép:

~~~json
{
  "status": "CONFIRMED",
  "total": {
    "amount": 1,
    "currency": "VND"
  }
}
~~~

đi thẳng vào entity đơn hàng sẽ bỏ qua những điều kiện quan trọng nếu server không kiểm soát.

Cần phân biệt:

- Dữ liệu đầu vào mà client được quyền yêu cầu.
- Giá trị do server tính.
- Trạng thái được dẫn xuất hoặc chỉ chuyển qua thao tác có kiểm tra.
- Trường chỉ dành cho người có quyền đặc biệt.

### 9.2. Hợp đồng cần rõ hơn tên field

Với mỗi trường, xác định kiểu, tính bắt buộc, miền giá trị, đơn vị và ý nghĩa của việc thiếu/null.

Với thao tác, xác định điều kiện trước, kết quả, lỗi và tác động được phép.

OpenAPI có thể mô tả nhiều phần của hợp đồng HTTP và schema. Nhưng việc mô hình hóa đúng tài nguyên còn cần quyết định nghiệp vụ; chỉ sinh schema từ entity không tự đưa ra những quyết định đó.

## 10. Ánh xạ ban đầu sang tương tác HTTP

Sau khi đã hiểu resource, có thể phác thảo:

| Nhu cầu | Tương tác minh họa | Ý nghĩa |
|---|---|---|
| Xem danh sách sản phẩm | `GET /products` | Đọc một tập resource theo quyền và bộ lọc |
| Xem một sản phẩm | `GET /products/prd_7` | Đọc representation của sản phẩm |
| Xem giỏ | `GET /carts/cart_91` | Đọc trạng thái giỏ hiện tại |
| Thêm dòng vào giỏ | `POST /carts/cart_91/items` | Yêu cầu tập dòng hàng xử lý dữ liệu thêm |
| Đặt số lượng của một dòng | `PATCH /carts/cart_91/items/line_1` | Sửa theo một định dạng và quy tắc patch được công bố |
| Bỏ dòng khỏi giỏ | `DELETE /carts/cart_91/items/line_1` | Xóa thành phần theo hợp đồng |
| Tạo đơn từ giỏ | `POST /orders` | Tạo một resource đơn hàng |
| Theo dõi đơn | `GET /orders/ord_204` | Đọc trạng thái và thông tin được phép |
| Theo dõi lần thanh toán | `GET /payments/pay_81` | Đọc một lần thanh toán cụ thể |

Bảng này không xác định toàn bộ API. Chẳng hạn, thêm một sản phẩm đã có trong giỏ là gộp số lượng hay tạo dòng mới phải được định nghĩa riêng.

Tương tự, ghi “PATCH” chưa đủ để biết request body có ý nghĩa gì. API phải công bố hợp đồng thay đổi và xử lý các giá trị không hợp lệ.

### 10.1. Method và mã trạng thái giúp kiểm tra mô hình

Nếu một thao tác đọc bằng `GET` lại tạo đơn hàng, có dấu hiệu đang trộn ý định đọc với tác động ghi.

Nếu resource vừa tạo không thể được tham chiếu hoặc theo dõi dù nghiệp vụ yêu cầu, cần xem lại định danh và representation.

Một vài kết quả minh họa:

- Tạo đơn thành công: `201 Created`.
- Đọc đơn thành công: `200 OK`.
- Không tìm thấy resource theo chính sách công bố: `404 Not Found`.
- Giỏ không còn ở trạng thái có thể đặt: có thể dùng `409 Conflict` theo hợp đồng.
- Dữ liệu request không hợp lệ: chọn mã lỗi phù hợp và cấu trúc lỗi nhất quán.

Không nên dùng bảng status thay cho phân tích nghiệp vụ. Cần biết nguyên nhân cụ thể trước khi chọn mã.

### 10.2. Mô hình không tự bảo đảm retry và concurrency

Hai request tạo đơn từ cùng một giỏ có thể đến gần nhau. Client cũng có thể gửi lại sau timeout.

Cần quyết định:

- Một giỏ được dùng tạo tối đa bao nhiêu đơn trong tình huống này?
- Việc tạo trùng bị ngăn bằng quy tắc nào?
- Có cơ chế idempotency cho lần thử tạo đơn không?
- Giá và tồn kho được kiểm tra ở thời điểm nào?
- Nếu giỏ bị sửa đồng thời, request nào được chấp nhận?

Đó là những phần phải được triển khai ở server. Việc chọn đúng danh từ `orders` không tự giải quyết các vấn đề này.

## 11. Tài nguyên không nhất thiết được lưu lâu dài

Ngoài đối tượng nghiệp vụ có lịch sử, API còn có thể biểu diễn:

- Kết quả tìm kiếm được xác định bằng URI và tham số.
- Tình trạng khả dụng được tính từ dữ liệu hiện tại.
- Một bản tổng hợp để phục vụ màn hình.
- Một công việc xuất báo cáo có thời hạn lưu kết quả.

Ví dụ, nếu xuất lịch sử đơn mất nhiều thời gian và client cần theo dõi:

~~~text
POST /order-export-jobs
GET  /order-export-jobs/job_81
~~~

Resource công việc có thể có trạng thái `QUEUED`, `RUNNING`, `SUCCEEDED` hoặc `FAILED` theo hợp đồng.

Không cần giả định mọi job được giữ vĩnh viễn. Nhưng cần công bố thời hạn, cách lấy kết quả và hành vi khi resource đã hết hạn.

Ngược lại, nếu một phép tính đơn giản được trả ngay và không cần theo dõi, không nhất thiết tạo một job chỉ để có thêm resource.

## 12. Liên hệ với Java/Spring: DTO thể hiện quyết định công khai

Một tập DTO minh họa bằng Java có hỗ trợ `record`:

~~~java
import java.util.List;

public final class OrderContracts {

    private OrderContracts() {
    }

    public record CreateOrderRequest(String cartId) {
    }

    public record MoneyView(long amount, String currency) {
    }

    public record OrderItemView(
        String productId,
        String productName,
        int quantity,
        MoneyView unitPrice
    ) {
    }

    public record OrderView(
        String id,
        String status,
        List<OrderItemView> items,
        MoneyView total
    ) {
    }
}
~~~

Tập DTO này cho thấy request tạo đơn chỉ chứa dữ liệu cần cho ý định tạo, trong khi response có những thông tin được server xác lập.

DTO chưa triển khai validation, tính tiền, phân quyền, transaction hoặc idempotency. Những phần đó vẫn cần nằm trong các thành phần phù hợp.

Trong một ứng dụng Spring:

- Controller nhận request và ánh xạ tương tác HTTP.
- Tầng nghiệp vụ thực hiện quy tắc tạo và thay đổi resource.
- Tầng lưu trữ giữ dữ liệu theo cấu trúc phù hợp.
- Thành phần ánh xạ tạo representation công khai.
- Cấu hình và kiểm thử xác nhận response khớp hợp đồng.

Không nên trả trực tiếp entity lưu trữ chỉ vì entity đã có đủ getter. Điều đó có thể làm lộ trường nội bộ, quan hệ không cần thiết hoặc khiến thay đổi database ảnh hưởng trực tiếp tới client.

Ngược lại, cũng không cần tạo một lớp cho mọi danh từ chỉ để mô hình trông đầy đủ. Số lượng class không phải thước đo chất lượng của mô hình resource.

## 13. Bài thực hành: ghi lại quyết định thay vì chỉ vẽ endpoint

Với yêu cầu bán hàng ở đầu bài, hãy lập một bảng thiết kế cho ba đối tượng: giỏ hàng, đơn hàng và thanh toán.

| Nội dung cần ghi | Câu hỏi hướng dẫn |
|---|---|
| Ý nghĩa nghiệp vụ | Đối tượng đại diện điều gì và ai cần dùng? |
| Định danh | Dùng giá trị nào, ổn định trong phạm vi nào? |
| Vòng đời | Có những trạng thái và điều kiện chuyển nào? |
| Thành phần | Phần nào nhúng, phần nào có định danh hoặc truy cập riêng? |
| Quan hệ | Liên hệ với những resource nào? |
| Quyền | Ai được đọc, tạo và thực hiện từng thao tác? |
| Request/response | Client gửi gì, server quyết định gì? |
| Bất biến | Những điều nào phải được bảo vệ khi có request đồng thời? |

Sau đó kiểm tra mô hình bằng các tình huống:

1. Sản phẩm đổi tên sau khi đơn đã được tạo.
2. Người mua sửa địa chỉ trong sổ địa chỉ.
3. Cùng một giỏ được gửi yêu cầu đặt hai lần.
4. Thanh toán lần đầu thất bại rồi người mua thử lại.
5. Người khác biết được ID của đơn hàng.
6. Một nhân viên muốn sửa tổng tiền bằng request trực tiếp.
7. Một báo cáo xuất chậm và cần được theo dõi.

Một mô hình tốt cần giải thích được dữ liệu nào thay đổi, dữ liệu nào được giữ lại, resource nào được tạo và quyền nào phải được kiểm tra trong từng tình huống.

Không cần thiết kế hết mọi endpoint trước khi trả lời. Những câu hỏi này có thể cho thấy mô hình ban đầu cần được điều chỉnh.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả |
|---|---|
| Mỗi bảng có một endpoint và trả nguyên các cột | Hợp đồng công khai phụ thuộc cấu trúc lưu trữ |
| Mỗi danh từ thành một resource độc lập | API quá vụn, client cần nhiều tương tác không cần thiết |
| Mỗi động từ thành một URL mà không tìm đối tượng chịu tác động | Giao diện khó thống nhất và khó thấy vòng đời |
| Mọi field response đều cho ghi ngược vào entity | Client có thể can thiệp trạng thái hoặc giá trị phải do server quyết định |
| Dùng dữ liệu hiện tại thay cho mọi snapshot lịch sử | Đơn cũ thay đổi ý nghĩa khi catalog hoặc hồ sơ thay đổi |
| Dùng ID khó đoán thay cho phân quyền | Người biết ID có thể truy cập trái phép |
| Coi một response tổng hợp là transaction xuyên nhiều nguồn | Đưa ra cam kết nhất quán mà hệ thống chưa bảo đảm |
| Ép mọi thao tác thành CRUD | Bỏ sót quy tắc và chuyển trạng thái nghiệp vụ |
| Chỉ đặt URI rồi coi mô hình đã xong | Thiếu quyền, hợp đồng, lỗi, retry và điều kiện đồng thời |

Các lựa chọn hợp lý có thể khác nhau giữa hai hệ thống có tên miền nghiệp vụ giống nhau. Điều cần duy trì là sự rõ ràng của ý nghĩa, trách nhiệm và hợp đồng.

## 15. Tự kiểm tra

### Câu hỏi

1. Resource có bắt buộc tương ứng một bảng hoặc một entity Java không?
2. Vì sao “tổng tiền” thường là giá trị của đơn thay vì resource có ID riêng?
3. Khi nào địa chỉ hoặc báo giá đáng được nhận diện như một resource riêng?
4. Tại sao nên phân biệt giỏ hàng với đơn hàng dù cả hai đều chứa dòng sản phẩm?
5. Đổi giá sản phẩm có nên tự thay giá trong một đơn đã được xác lập không?
6. Một dòng giỏ hàng có bắt buộc có ID duy nhất trên toàn hệ thống không?
7. Thấy trường `status` trong response có nghĩa client được tự PATCH mọi giá trị vào đó không?
8. URI của đơn đã khó đoán thì có thể bỏ kiểm tra quyền không?
9. Một lần thanh toán thất bại rồi thử lại có luôn chỉ cần một boolean `paid` không?
10. Mô hình resource đúng có tự ngăn tạo đơn trùng khi retry không?

### Gợi ý trả lời

1. Không. Resource là khái niệm công khai để tương tác; cấu trúc lưu trữ và class là những quyết định triển khai riêng.
2. Vì trong tình huống này nó là kết quả tính theo quy tắc của đơn, chưa có nhu cầu nhận diện và quản lý vòng đời độc lập.
3. Khi cần định danh, tra cứu, cập nhật, lựa chọn hoặc theo dõi vòng đời riêng; đồng thời vẫn có thể dùng một snapshot giá trị trong resource khác.
4. Vì giỏ phản ánh ý định thay đổi, còn đơn phản ánh những thông tin đã được hệ thống ghi nhận theo một hợp đồng và vòng đời khác.
5. Trong mô hình minh họa, không. Giá trong đơn giữ ý nghĩa tại thời điểm được xác lập; thay đổi lịch sử phải có quy tắc riêng nếu được cho phép.
6. Không. Có thể chỉ duy nhất trong phạm vi giỏ, miễn là URI và kiểm tra quan hệ xác định đúng dòng.
7. Không. Field đọc và field ghi có quyền, quy tắc và điều kiện khác nhau.
8. Không. ID không thay thế xác thực hoặc phân quyền trên resource.
9. Không. Nếu cần theo dõi và đối soát từng lần thử, nên mô hình hóa thông tin chi tiết phù hợp thay vì chỉ giữ một cờ.
10. Không. Cần quy tắc nghiệp vụ, kiểm soát đồng thời và cơ chế idempotency phù hợp.

Trước khi chốt một tập URI, hãy có khả năng giải thích **resource đại diện điều gì, được nhận diện thế nào, thay đổi theo vòng đời nào và ai được tương tác với nó**. Những quyết định đó tạo nền tảng cho thiết kế HTTP và hợp đồng dữ liệu rõ ràng ở các bài tiếp theo.
