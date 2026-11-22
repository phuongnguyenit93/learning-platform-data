# Vì sao cùng một thuật ngữ có thể mang nghĩa khác ở các ngữ cảnh

Trong một tổ chức, nhiều bộ phận thường sử dụng cùng một từ để nói về công việc của mình. Từ “khách hàng” có thể xuất hiện trong bán hàng, chăm sóc khách hàng, kế toán và giao hàng. Từ “sản phẩm” có thể được dùng trong danh mục hàng hóa, quản lý kho, định giá và bảo hành. Mọi người đều hiểu từ đó theo kinh nghiệm của họ, nhưng điều họ đang nói đến có thể khác nhau về mục đích, thuộc tính, vòng đời và quy tắc.

Domain-Driven Design (DDD) xem đây là một đặc điểm tự nhiên của miền nghiệp vụ phức tạp. Một thuật ngữ không nhất thiết phải có một định nghĩa duy nhất trên toàn hệ thống. Trong mỗi **bounded context (ngữ cảnh giới hạn)**, thuật ngữ thuộc về một mô hình và có ý nghĩa được xác định bởi ngôn ngữ, quy tắc và trách nhiệm của context đó. Cùng một từ có thể mang nghĩa khác ở context khác mà không làm cho mô hình trở nên sai, miễn là ranh giới và cách trao đổi giữa các context được làm rõ.

Bài học này giải thích vì sao sự khác biệt đó xuất hiện, cách nhận biết nó, cách mô hình hóa các nghĩa theo từng bounded context và cách chuyển thông tin giữa các context mà không làm mất ý nghĩa nghiệp vụ.

## 1. Bounded context xác định phạm vi của một mô hình

Một miền nghiệp vụ lớn thường có nhiều năng lực và bộ phận với mục tiêu khác nhau. Nếu cố gắng mô tả tất cả bằng một mô hình duy nhất, nhóm sẽ phải tìm những khái niệm quá tổng quát, chứa nhiều thuộc tính và quy tắc không liên quan. Kết quả thường là một mô hình khó hiểu, khó thay đổi và không phản ánh chính xác cách từng bộ phận làm việc.

**Bounded context** là ranh giới trong đó một mô hình miền và ngôn ngữ chung được định nghĩa, sử dụng và duy trì nhất quán. Bên trong ranh giới đó, nhóm có thể hiểu một thuật ngữ theo một ý nghĩa cụ thể, gắn nó với các hành vi và quy tắc tương ứng. Khi đi qua ranh giới sang context khác, cùng thuật ngữ có thể được hiểu theo mô hình khác.

Ví dụ, một doanh nghiệp bán hàng trực tuyến có thể có các bounded context như:

- **Bán hàng (Sales):** quản lý cơ hội bán, khách mua, đơn hàng và chính sách bán.
- **Danh mục sản phẩm (Catalog):** quản lý thông tin mô tả, phân loại và cách sản phẩm được giới thiệu.
- **Kho vận (Warehouse):** quản lý tồn kho, vị trí lưu trữ, lấy hàng và đóng gói.
- **Thanh toán (Billing/Payment):** quản lý khoản phải thu, giao dịch, hóa đơn và hoàn tiền.
- **Chăm sóc khách hàng (Customer Support):** quản lý yêu cầu hỗ trợ, lịch sử tương tác và cam kết xử lý.

Các context này có thể cùng nói về một khách hàng hoặc một sản phẩm, nhưng chúng không nhất thiết cần cùng một mô hình `Customer` hoặc `Product`. Mỗi context chọn những thông tin và quy tắc cần thiết để thực hiện trách nhiệm của mình.

Bounded context không đơn thuần là một package, một service, một database hay một nhóm người. Nó là ranh giới của mô hình và ngôn ngữ. Trong một hệ thống, một bounded context có thể được triển khai bằng một hoặc nhiều thành phần kỹ thuật; ngược lại, một ứng dụng hoặc database có thể chứa nhiều mô hình nếu ranh giới ngôn ngữ của chúng vẫn được xác định rõ.

## 2. Vì sao cùng một từ có nhiều ý nghĩa?

Sự khác nhau về ý nghĩa thường xuất phát từ việc các bộ phận nhìn cùng một thực thể ngoài đời qua những mục tiêu và trách nhiệm khác nhau. Các lý do phổ biến gồm:

### 2.1. Mỗi bộ phận giải quyết một vấn đề khác nhau

Một bộ phận bán hàng cần biết ai có nhu cầu mua, người đó quan tâm đến sản phẩm nào và có thể ký kết giao dịch hay không. Bộ phận kế toán cần biết chủ thể nào chịu nghĩa vụ thanh toán, có hạn mức tín dụng hay không và đang còn khoản phải thu nào. Bộ phận giao hàng cần biết hàng sẽ được chuyển đến ai, tại địa chỉ nào và ai có thể nhận hàng.

Ba bộ phận có thể cùng sử dụng từ “khách hàng”, nhưng câu hỏi nghiệp vụ của họ khác nhau. Vì vậy, thông tin được xem là quan trọng và các quy tắc áp dụng cũng khác nhau.

### 2.2. Mỗi context có trách nhiệm và quyền quyết định riêng

Context bán hàng có thể chịu trách nhiệm xác nhận một đơn hàng. Context kho chịu trách nhiệm xác nhận việc lấy và đóng gói hàng. Context thanh toán chịu trách nhiệm ghi nhận giao dịch và xác định khoản tiền đã được thanh toán. Không context nào nên tự ý quyết định thay cho context sở hữu quy tắc đó.

Nếu các context dùng một mô hình chung nhưng không làm rõ quyền sở hữu, một thay đổi ở bộ phận này có thể vô tình làm thay đổi hành vi của bộ phận khác. Ranh giới bounded context giúp xác định mô hình nào sở hữu quy tắc nào.

### 2.3. Cùng một đối tượng có vòng đời khác nhau

Một đối tượng được nhìn nhận theo vòng đời phù hợp với công việc của từng context. Trong bán hàng, đơn hàng có thể trải qua các trạng thái nháp, đã xác nhận, đã hủy hoặc đã hoàn tất. Trong kho, nhiệm vụ lấy hàng có thể ở trạng thái chờ, đang lấy, đã đóng gói hoặc bị dừng. Hai vòng đời có liên quan nhưng không giống nhau.

Nếu ép chúng vào một trạng thái chung như `OrderStatus`, nhóm có thể tạo ra nhiều trạng thái pha trộn, chẳng hạn `WAITING_FOR_PICKING`, `PAYMENT_FAILED`, `RETURNED_TO_SENDER` và `CANCELLED_BY_CUSTOMER`. Các trạng thái này có thể thuộc những quy trình và chủ sở hữu khác nhau.

### 2.4. Quy tắc và bất biến khác nhau

Trong context bán hàng, một khách hàng có thể được phép đặt đơn khi đáp ứng điều kiện bán. Trong context tín dụng, cùng khách hàng đó có thể bị giới hạn số dư công nợ. Trong context chăm sóc khách hàng, nhân viên có thể tiếp nhận yêu cầu ngay cả khi khách hàng đang có khoản nợ quá hạn.

Mỗi context bảo vệ những bất biến cần thiết cho trách nhiệm của mình. Sự khác nhau về quy tắc khiến cùng một thuật ngữ có thể đại diện cho những cấu trúc và hành vi khác nhau.

### 2.5. Mức độ chi tiết và dữ liệu cần thiết khác nhau

Danh mục sản phẩm cần tên hiển thị, mô tả, hình ảnh và phân loại. Kho cần mã hàng, đơn vị lưu trữ, số lượng khả dụng và vị trí. Định giá cần bảng giá, điều kiện áp dụng, thời hạn hiệu lực và quy tắc chiết khấu. Không context nào cần toàn bộ dữ liệu của các context còn lại chỉ vì tất cả đều nói về “sản phẩm”.

Việc chọn đúng mức độ chi tiết giúp mô hình nhỏ gọn và tập trung. Một context có thể dùng một bản biểu diễn rút gọn của khái niệm được context khác quản lý.

## 3. Ví dụ: “Khách hàng” trong các bounded context

“Khách hàng” là ví dụ quen thuộc vì hầu hết hệ thống doanh nghiệp đều có nhiều bộ phận tương tác với khách hàng. Tuy nhiên, không có nghĩa mọi bộ phận cần dùng cùng một mô hình khách hàng.

| Bounded context | “Khách hàng” có ý nghĩa gì? | Thông tin quan trọng | Quy tắc hoặc hành vi tiêu biểu |
| --- | --- | --- | --- |
| Bán hàng | Người hoặc tổ chức tham gia giao dịch mua | Nhu cầu, phân khúc, điều kiện bán, người liên hệ | Có đủ điều kiện để tạo hoặc xác nhận đơn hàng không? |
| Thanh toán | Chủ thể chịu nghĩa vụ thanh toán | Thông tin thanh toán, hạn mức, số dư, điều khoản tín dụng | Có thể ghi nhận khoản phải thu hoặc hoàn tiền không? |
| Giao hàng | Người nhận hoặc địa điểm nhận hàng | Tên người nhận, địa chỉ, chỉ dẫn giao, khung giờ | Có thể giao tại địa chỉ này và xác nhận người nhận không? |
| Chăm sóc khách hàng | Chủ thể gửi yêu cầu và tương tác với tổ chức | Lịch sử liên hệ, yêu cầu hỗ trợ, mức độ ưu tiên | Yêu cầu nào cần được tiếp nhận và xử lý trước? |

Trong bán hàng, một công ty có thể là khách hàng dù người liên hệ đặt đơn là một nhân viên. Trong giao hàng, người nhận có thể là một cá nhân khác. Trong thanh toán, pháp nhân chịu trách nhiệm trả tiền có thể là công ty mẹ. Nếu mô hình chỉ có một `Customer` với một trường `name`, nhóm sẽ khó biểu diễn chính xác các quan hệ này.

Một thiết kế có thể gồm các mô hình riêng:

```text
Sales context
  Buyer
    - buyerId
    - salesSegment
    - salesEligibility

Payment context
  PayerAccount
    - payerAccountId
    - creditLimit
    - outstandingBalance

Delivery context
  Recipient
    - recipientName
    - deliveryAddress
    - deliveryInstructions

Support context
  SupportCustomer
    - supportCustomerId
    - contactHistory
    - supportPreferences
```

Các tên trên là ví dụ minh họa. Tổ chức có thể chọn thuật ngữ khác dựa trên ngôn ngữ thực tế. Điều quan trọng là mỗi mô hình thể hiện đúng trách nhiệm và quy tắc của context sở hữu nó.

Các mô hình có thể cùng tham chiếu một mã khách hàng toàn cục nếu tổ chức có cơ chế định danh phù hợp. Tuy nhiên, việc cùng giữ một mã tham chiếu không có nghĩa chúng phải dùng chung một entity, cùng cấu trúc dữ liệu hoặc cùng vòng đời. Mã định danh giúp liên kết thông tin; bounded context vẫn quyết định ý nghĩa của mô hình nội bộ.

## 4. Ví dụ: “Sản phẩm” và “đơn hàng” cũng thay đổi theo ngữ cảnh

### 4.1. Sản phẩm trong danh mục, kho và định giá

Trong context danh mục, sản phẩm là thứ được giới thiệu cho người mua. Mô hình quan tâm đến tên, mô tả, hình ảnh, thuộc tính hiển thị và phân loại. Trong context kho, đơn vị quản lý có thể là SKU hoặc đơn vị lưu trữ; điều quan trọng là số lượng, vị trí và khả năng đáp ứng. Trong context định giá, một sản phẩm được xem xét cùng bảng giá, tiền tệ, thời hạn và điều kiện chiết khấu.

| Context | Cách hiểu “sản phẩm” | Câu hỏi mà mô hình cần trả lời |
| --- | --- | --- |
| Danh mục | Sản phẩm được trình bày cho người mua | Sản phẩm có tên, mô tả và thuộc tính hiển thị nào? |
| Kho | Hàng hóa hoặc SKU cần quản lý vật lý | Còn bao nhiêu đơn vị, nằm ở đâu và có thể lấy không? |
| Định giá | Đối tượng áp dụng một chính sách giá | Giá nào có hiệu lực với khách hàng và thời điểm này? |
| Bảo hành | Sản phẩm hoặc thiết bị đã bán cần được hỗ trợ | Có thuộc phạm vi bảo hành và còn thời hạn không? |

Một sản phẩm danh mục có thể có nhiều SKU, còn một SKU có thể có nhiều lô hàng trong kho. Giá bán có thể thay đổi theo thời gian hoặc phân khúc khách hàng. Nếu tất cả các khái niệm này bị gộp vào một `Product` duy nhất, mô hình dễ trở nên cồng kềnh và khó bảo vệ quy tắc.

### 4.2. Đơn hàng trong bán hàng và kho

Trong context bán hàng, `Order` biểu diễn cam kết mua của khách và các quy tắc về giá, chiết khấu, xác nhận hoặc hủy. Trong context kho, công việc chính là lấy hàng, đóng gói và bàn giao. Kho có thể quản lý `PickingTask` hoặc `FulfillmentOrder` với trạng thái riêng.

Một đơn bán hàng có thể tạo ra nhiều nhiệm vụ lấy hàng nếu hàng nằm ở nhiều kho. Một nhiệm vụ lấy hàng có thể chỉ chứa một phần dòng hàng của đơn. Khi kho xác nhận đã đóng gói, điều đó không nhất thiết có nghĩa đơn bán hàng đã hoàn tất. Hai context cần trao đổi trạng thái qua hợp đồng rõ ràng.

Ví dụ, khi bán hàng phát sự kiện `OrderConfirmed`, kho có thể tạo nhiệm vụ lấy hàng. Khi kho phát sự kiện `PickingCompleted`, bán hàng hoặc điều phối giao hàng có thể tiếp tục quy trình. Mỗi context sử dụng thuật ngữ phản ánh trách nhiệm của chính mình.

## 5. Khác nghĩa giữa các context không phải là mâu thuẫn

Khi cùng một từ có nhiều nghĩa, người mới thường cho rằng tổ chức cần chọn một định nghĩa đúng và buộc mọi bộ phận dùng định nghĩa đó. Cách nghĩ này bỏ qua việc mỗi bộ phận có thể đang giải quyết một vấn đề khác nhau.

Hãy phân biệt hai tình huống:

- **Mơ hồ bên trong một context:** cùng một nhóm dùng từ “đơn hàng” lúc để chỉ cam kết mua, lúc lại để chỉ phiếu lấy hàng, nhưng không có quy ước rõ. Đây là vấn đề cần giải quyết vì mô hình và ngôn ngữ trong cùng ranh giới đang thiếu nhất quán.
- **Khác biệt có chủ đích giữa các context:** bán hàng dùng “đơn hàng” cho cam kết mua, kho dùng “nhiệm vụ lấy hàng” cho công việc nội bộ. Hai mô hình có thể cùng liên quan đến một giao dịch nhưng mỗi mô hình trả lời một câu hỏi khác nhau. Đây là khác biệt hợp lệ nếu được xác định và tích hợp rõ ràng.

Do đó, câu hỏi cần đặt ra không phải là “từ này có một nghĩa đúng duy nhất không?”, mà là “trong context nào, ai dùng từ này, để mô tả điều gì và theo quy tắc nào?”.

Sự khác nhau cũng không có nghĩa mọi context đều phải đặt tên hoàn toàn khác nhau. Hai context có thể cùng dùng một từ nếu ý nghĩa phù hợp trong từng nơi. Điều cần tránh là giả định rằng tên giống nhau chứng minh mô hình giống nhau, hoặc tên khác nhau chứng minh hai khái niệm không liên quan.

## 6. Ngôn ngữ chung được duy trì trong từng bounded context

**Ubiquitous Language (ngôn ngữ chung)** là ngôn ngữ được chuyên gia nghiệp vụ và nhóm phát triển cùng sử dụng trong một bounded context. Nó xuất hiện trong cuộc trao đổi, tài liệu, ví dụ, mô hình, tên lớp, phương thức, sự kiện và kiểm thử.

Ngôn ngữ chung có phạm vi. Một thuật ngữ được thống nhất trong context bán hàng không tự động trở thành định nghĩa chuẩn cho context kho. Mỗi context có thể có từ điển riêng, trong đó ghi rõ:

- Thuật ngữ chuẩn và định nghĩa trong context.
- Các bí danh hoặc tên cũ còn gặp trong tài liệu và dữ liệu.
- Các thuật ngữ dễ nhầm với khái niệm hiện tại.
- Các quy tắc, trạng thái và hành vi liên quan.
- Những thuật ngữ tương ứng trong context khác, nếu có.
- Người hoặc vai trò có trách nhiệm xác nhận ý nghĩa.

Ví dụ, từ “khách hàng” có thể được ghi trong từ điển của context bán hàng là “người hoặc tổ chức tham gia giao dịch mua”. Trong context thanh toán, từ này có thể được thay bằng “chủ thể thanh toán” nếu thuật ngữ đó diễn đạt chính xác trách nhiệm pháp lý và tài chính hơn.

Việc ghi nhận khác biệt giúp thành viên mới hiểu rằng các mô hình đang phục vụ những mục tiêu khác nhau. Nó cũng giúp nhóm tránh vô tình dùng lại một định nghĩa ở nơi nó không còn đúng.

## 7. Các context trao đổi với nhau như thế nào?

Mỗi bounded context có quyền sở hữu mô hình và quy tắc nội bộ của mình. Tuy vậy, các quy trình doanh nghiệp thường đi qua nhiều context. Bán hàng cần kho thực hiện lấy hàng; kho cần biết những dòng hàng nào phải chuẩn bị; thanh toán cần biết nghĩa vụ tiền phát sinh; chăm sóc khách hàng cần biết lịch sử xử lý giao dịch.

Để phối hợp, các context cần một hợp đồng tích hợp. Hợp đồng này xác định thông tin được gửi, ý nghĩa của nó, thời điểm gửi và cách xử lý khi thông tin thay đổi hoặc không hợp lệ.

### 7.1. Trao đổi qua sự kiện nghiệp vụ

Một context có thể công bố sự kiện mô tả điều đã xảy ra trong mô hình của nó. Context khác tiếp nhận sự kiện và chuyển thành hành động hoặc khái niệm phù hợp với mô hình nội bộ.

```text
Sales context                    Warehouse context
--------------                    -----------------
OrderConfirmed  --------------->  CreatePickingTask
                                  (tạo nhiệm vụ lấy hàng)

PickingCompleted <-------------  PickingCompleted
                                  (hoàn tất lấy hàng)
```

Tên sự kiện và payload cần có ý nghĩa rõ trong hợp đồng. Context nhận không nên giả định rằng một trường `status` có cùng ý nghĩa với trường cùng tên ở context gửi. Nếu cần, context nhận dùng bộ chuyển đổi để diễn giải thông tin theo ngôn ngữ của mình.

### 7.2. Chuyển đổi mô hình tại ranh giới

Một context có thể chuyển dữ liệu từ hợp đồng bên ngoài thành mô hình nội bộ. Ví dụ, sự kiện `OrderConfirmed` từ bán hàng có thể được ánh xạ thành một `PickingTask` trong kho. Kho lưu mã tham chiếu đến đơn bán hàng để truy vết, nhưng các quy tắc lấy hàng vẫn thuộc mô hình kho.

Khi hệ thống bên ngoài có mô hình phức tạp hoặc không phù hợp với ngôn ngữ nội bộ, nhóm có thể dùng **Anti-Corruption Layer (lớp chống ăn mòn)** để chuyển đổi dữ liệu và ý nghĩa. Lớp này bảo vệ mô hình của context nhận khỏi việc phụ thuộc trực tiếp vào cấu trúc và thuật ngữ của context gửi.

Không phải mọi tích hợp đều cần một lớp chống ăn mòn riêng. Với hợp đồng nhỏ và ổn định, một adapter hoặc mapper đơn giản có thể đủ. Cấu trúc chuyển đổi nên tương xứng với mức độ khác biệt và rủi ro của hai mô hình.

### 7.3. Context map làm rõ quan hệ giữa các mô hình

**Context map** mô tả các bounded context và quan hệ giữa chúng. Nó giúp nhóm thấy context nào cung cấp thông tin, context nào tiêu thụ, nơi nào có phụ thuộc và cách hai bên phối hợp.

Một context map không chỉ vẽ các hộp và mũi tên. Nhóm cần làm rõ hợp đồng, quyền quyết định và cách chuyển đổi ngôn ngữ. Các mẫu quan hệ như Customer-Supplier, Conformist, Published Language, Shared Kernel hoặc Anti-Corruption Layer có thể giúp diễn tả những cách phối hợp thường gặp. Việc chọn mẫu nào phụ thuộc vào mức độ kiểm soát, quyền thương lượng và nhu cầu bảo vệ mô hình của từng bên.

Ví dụ, nếu context bán hàng công bố sự kiện theo một ngôn ngữ ổn định, context kho có thể tiêu thụ hợp đồng đã công bố và ánh xạ sang mô hình kho. Nếu context nhận phải tuân theo mô hình của nhà cung cấp bên ngoài, nhóm cần cân nhắc cách bảo vệ ngôn ngữ nội bộ khỏi những thay đổi hoặc khái niệm không phù hợp.

## 8. Cách khám phá và quyết định ý nghĩa theo context

Khi một thuật ngữ xuất hiện trong nhiều bộ phận, nhóm có thể dùng quy trình sau để xác định liệu nó có đang đại diện cho những khái niệm khác nhau hay không.

### Bước 1: Thu thập cách dùng thực tế

Ghi lại từ ngữ được dùng trong cuộc họp, biểu mẫu, báo cáo, API và thao tác vận hành. Ghi rõ ai sử dụng, ở bộ phận nào, trong tình huống nào và đang đưa ra quyết định gì.

Đừng bắt đầu bằng cách áp một định nghĩa chung. Hãy giữ nguyên cách diễn đạt ban đầu để nhận diện sự khác biệt trong thực tế.

### Bước 2: Hỏi về mục tiêu và trách nhiệm

Với mỗi cách dùng, hỏi: “Bộ phận này đang cố hoàn thành việc gì?”, “Ai chịu trách nhiệm về kết quả?” và “Quyết định nào cần được đưa ra?”. Nếu mục tiêu và trách nhiệm khác nhau, mô hình có thể cần những khái niệm riêng.

### Bước 3: So sánh thông tin, hành vi và vòng đời

Lập bảng so sánh các thuộc tính cần thiết, hành vi, trạng thái, quy tắc và sự kiện. Đặc biệt chú ý những điểm khiến một context phải thay đổi mô hình khi context khác thay đổi.

Nếu hai mô hình chỉ khác nhau ở một vài trường trình bày nhưng cùng mục tiêu, danh tính và quy tắc, có thể chưa cần tách. Nếu chúng có vòng đời và bất biến riêng, đó là bằng chứng mạnh cho sự khác biệt về mô hình.

### Bước 4: Xác định ranh giới bounded context

Nhóm xác định nơi nào cần một ngôn ngữ và mô hình nhất quán. Ranh giới nên dựa trên năng lực nghiệp vụ, trách nhiệm, quy tắc và cách tổ chức làm việc. Không nên tách context chỉ vì hai nhóm có hai database, cũng không nên gộp chúng chỉ vì đang dùng chung một bảng dữ liệu.

### Bước 5: Thống nhất thuật ngữ trong từng context

Chuyên gia nghiệp vụ xác nhận định nghĩa và cách dùng. Nhóm phát triển đưa thuật ngữ đó vào mô hình, mã nguồn và kiểm thử. Nếu cùng một từ được dùng với hai nghĩa trong một context, hãy chọn tên rõ hơn hoặc ghi nhận quy ước để loại bỏ sự mơ hồ.

### Bước 6: Định nghĩa hợp đồng giữa các context

Xác định thông tin nào cần được chia sẻ, context nào sở hữu thông tin gốc, sự kiện hoặc API nào được dùng và cách chuyển đổi sang mô hình bên nhận. Tránh chia sẻ trực tiếp entity hoặc cấu trúc nội bộ khi hai context có mô hình khác nhau.

### Bước 7: Kiểm chứng bằng tình huống thực tế

Chọn các trường hợp bình thường và ngoại lệ để kiểm tra định nghĩa. Ví dụ, cùng một khách hàng đặt hàng cho người khác nhận, một pháp nhân thanh toán cho nhiều đơn vị mua, hoặc một sản phẩm có nhiều SKU. Nếu mô hình không giải thích được tình huống, nhóm cần xem lại định nghĩa hoặc ranh giới.

### Bước 8: Duy trì khi nghiệp vụ thay đổi

Khi trách nhiệm của bộ phận, quy trình hoặc chính sách thay đổi, nhóm xem lại mô hình và hợp đồng liên context. Một từ có thể đổi nghĩa theo thời gian; từ điển, tài liệu tích hợp, mã nguồn và kiểm thử cần được cập nhật đồng bộ.

## 9. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Cố tìm một định nghĩa duy nhất cho mọi bộ phận | Mô hình trở nên quá tổng quát và không bảo vệ được quy tắc riêng | Định nghĩa thuật ngữ trong từng bounded context |
| Dùng một entity chung cho mọi context | Các thuộc tính và hành vi không liên quan bị trộn lẫn | Xây dựng mô hình riêng theo trách nhiệm; dùng định danh hoặc hợp đồng để liên kết khi cần |
| Cho rằng tên giống nhau nghĩa là cùng một khái niệm | Bỏ qua khác biệt về vòng đời, mục tiêu và quy tắc | So sánh hành vi, bất biến và ngữ cảnh sử dụng |
| Cho rằng tên khác nhau luôn là hai khái niệm không liên quan | Tạo mô hình trùng lặp và chuyển đổi không cần thiết | Kiểm tra mục đích và quy tắc trước khi tách |
| Chia sẻ trực tiếp cấu trúc nội bộ qua API | Thay đổi của một context lan sang context khác | Công bố hợp đồng rõ ràng và chuyển đổi ở ranh giới |
| Dùng một trường trạng thái cho nhiều quy trình | Trạng thái mơ hồ và chuyển trạng thái không hợp lệ | Để mỗi context sở hữu vòng đời của mô hình mình |
| Không ghi lại khác biệt ngôn ngữ | Thành viên mới và nhóm tích hợp dễ dùng sai thuật ngữ | Duy trì từ điển theo context và context map |
| Tách context chỉ theo tổ chức hoặc hạ tầng | Ranh giới kỹ thuật không phản ánh ranh giới mô hình | Dựa vào năng lực, quy tắc và trách nhiệm nghiệp vụ |

Một mô hình chung có thể hữu ích khi các bên thật sự chia sẻ cùng một khái niệm và cùng chịu trách nhiệm duy trì nó. Tuy nhiên, việc tái sử dụng nên xuất phát từ sự thống nhất về ý nghĩa và quy tắc, không chỉ từ mong muốn tránh viết mã trùng lặp.

## 10. Nguyên tắc thực hành

Khi làm việc với những thuật ngữ xuất hiện ở nhiều context, nhóm nên nhớ các nguyên tắc sau:

- **Ý nghĩa luôn gắn với ngữ cảnh.** Hỏi ai đang dùng từ, trong quy trình nào và để đưa ra quyết định gì.
- **Mỗi bounded context sở hữu mô hình của mình.** Context quyết định những thuộc tính, hành vi và bất biến cần thiết cho trách nhiệm của nó.
- **Ngôn ngữ chung có phạm vi.** Thống nhất thuật ngữ trong context tương ứng; ghi nhận khác biệt khi cùng từ xuất hiện ở nơi khác.
- **Tên giống nhau không chứng minh mô hình giống nhau.** Kiểm tra mục tiêu, vòng đời, hành vi và quy tắc trước khi chia sẻ cấu trúc.
- **Tên khác nhau không tự động đòi hỏi hai mô hình.** Xác minh xem chúng có thực sự biểu diễn các khái niệm khác nhau không.
- **Giữ rõ quyền sở hữu dữ liệu và quy tắc.** Context nào chịu trách nhiệm cho một quyết định thì context đó bảo vệ quy tắc tương ứng.
- **Tích hợp bằng hợp đồng có ý nghĩa.** Chia sẻ thông tin cần thiết và chuyển đổi ở ranh giới; tránh để context phụ thuộc vào chi tiết nội bộ của nhau.
- **Kiểm chứng bằng tình huống.** Dùng ví dụ và phản ví dụ để xác nhận rằng mỗi định nghĩa phù hợp với công việc thật.
- **Cập nhật khi hiểu biết thay đổi.** Mô hình và ngôn ngữ chung cần phát triển cùng nghiệp vụ.

Trong DDD, cùng một thuật ngữ mang nghĩa khác nhau ở các bounded context là điều có thể dự đoán trong một miền phức tạp. Bằng cách xác định ranh giới mô hình, làm rõ mục tiêu và quy tắc của từng context, rồi định nghĩa hợp đồng trao đổi giữa chúng, nhóm có thể giữ ngôn ngữ rõ ràng mà vẫn phối hợp được toàn hệ thống.

## 11. Câu hỏi tự kiểm tra

1. Bounded context xác định điều gì trong DDD và vì sao nó không đơn thuần là một service hoặc database?
2. Nêu ít nhất ba lý do khiến cùng một thuật ngữ có thể mang nghĩa khác nhau giữa các bộ phận.
3. Vì sao “khách hàng” trong bán hàng, thanh toán và giao hàng có thể cần những mô hình riêng?
4. Phân biệt sự mơ hồ trong một bounded context với sự khác biệt có chủ đích giữa hai bounded context.
5. Vì sao hai context có thể tham chiếu cùng một mã khách hàng nhưng vẫn duy trì entity và vòng đời riêng?
6. Hãy giải thích sự khác nhau giữa “sản phẩm” trong danh mục và “sản phẩm” trong kho.
7. Khi đơn bán hàng được xác nhận, vì sao kho có thể tạo `PickingTask` thay vì dùng chung entity `Order`?
8. Context map giúp làm rõ những thông tin và quan hệ nào giữa các bounded context?
9. Anti-Corruption Layer hỗ trợ bảo vệ mô hình của context nhận như thế nào?
10. Hãy chọn một thuật ngữ được nhiều bộ phận trong một tổ chức sử dụng, mô tả ý nghĩa trong ít nhất hai context và đề xuất hợp đồng trao đổi phù hợp.
