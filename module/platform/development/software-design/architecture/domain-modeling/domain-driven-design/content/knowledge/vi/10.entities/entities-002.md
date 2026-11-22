# Phân biệt danh tính nghiệp vụ với khóa kỹ thuật của bản ghi

Trong một hệ thống bán hàng, một đơn có thể được nhận diện bằng số đơn `ORD-2026-00125`, bằng một UUID như `8f4a...`, hoặc bằng khóa số `48291` trong bảng dữ liệu. Cả ba giá trị đều có thể trỏ đến cùng một đơn, nhưng chúng được tạo ra để phục vụ những mục đích khác nhau. Số đơn giúp nhân viên và khách hàng trao đổi về giao dịch. UUID có thể là danh tính mà mô hình domain sử dụng. Khóa số có thể chỉ là khóa chính do cơ sở dữ liệu quản lý.

Trong Domain-Driven Design (DDD), **Entity** là đối tượng được nhận diện bằng danh tính và có thể thay đổi trạng thái trong suốt vòng đời. Danh tính giúp phân biệt một Entity với Entity khác ngay cả khi các thuộc tính của chúng giống nhau hoặc thay đổi theo thời gian. Khóa chính của một bản ghi là cơ chế kỹ thuật để lưu trữ và tham chiếu dữ liệu. Hai khái niệm có thể dùng cùng một giá trị, nhưng không vì vậy mà có cùng ý nghĩa.

Nếu đồng nhất danh tính nghiệp vụ với khóa kỹ thuật, mô hình dễ phụ thuộc vào cấu trúc lưu trữ. Đội phát triển có thể dùng số thứ tự của database làm mã đơn trong mọi API, hoặc xem một số điện thoại là danh tính bất biến của khách hàng. Những lựa chọn này thường gây khó khăn khi đổi database, hợp nhất dữ liệu, tích hợp hệ thống hoặc xử lý thay đổi nghiệp vụ.

Sau bài học này, bạn có thể:

- Giải thích danh tính của Entity và vai trò của business identifier.
- Phân biệt Entity identity, business key và database primary key.
- Nhận diện natural key, surrogate key và composite key.
- Chọn cách biểu diễn danh tính trong domain model và persistence model.
- Xác định quy tắc so sánh Entity và xử lý định danh khi tích hợp nhiều Bounded Context.

## 1. Danh tính của Entity là gì?

Một Entity là đối tượng có danh tính riêng trong một Bounded Context. Danh tính trả lời câu hỏi: **“Đây có phải chính đối tượng mà chúng ta đã nói đến trước đó không?”** Câu trả lời không phụ thuộc hoàn toàn vào tên, địa chỉ, trạng thái hoặc những thuộc tính hiện tại.

Ví dụ, khách hàng Nguyễn An đổi địa chỉ email và số điện thoại. Hồ sơ khách hàng vẫn là cùng một khách hàng trong hệ thống quản lý khách hàng. Một Order được tạo hôm nay có thể đổi địa chỉ giao hàng hoặc chuyển trạng thái từ `Pending` sang `Confirmed`, nhưng vẫn là chính Order đó.

Có thể nhận diện Entity qua các đặc điểm:

- Có danh tính để phân biệt với các đối tượng cùng loại.
- Có vòng đời; trạng thái hoặc thuộc tính có thể thay đổi.
- Các hành vi và quy tắc nghiệp vụ thường gắn với danh tính đó.
- Những tham chiếu đến Entity cần tiếp tục chỉ đến cùng đối tượng khi dữ liệu thay đổi.

Hãy so sánh hai khách hàng có cùng tên và ngày sinh. Họ vẫn có thể là hai người khác nhau. Ngược lại, cùng một khách hàng đổi tên hiển thị sau một thay đổi hợp pháp vẫn là cùng một Entity. Vì thế, không thể dùng toàn bộ thuộc tính mô tả để xác định danh tính.

### Danh tính khác trạng thái

Danh tính trả lời “đối tượng nào”; trạng thái trả lời “đối tượng đang ở tình trạng nào”.

| Khía cạnh | Ví dụ của Order |
|---|---|
| Danh tính | `OrderId = 8f4a...` |
| Số định danh nghiệp vụ | `ORD-2026-00125` |
| Trạng thái hiện tại | `Confirmed` |
| Thuộc tính có thể thay đổi | Địa chỉ giao hàng, ghi chú, thời điểm cập nhật |

Order chuyển từ `Draft` sang `Placed`, rồi `Confirmed` hoặc `Cancelled`. Những thay đổi này không tạo ra một Order mới. Nếu một khách hủy Order và tạo đơn khác, Order mới cần danh tính mới dù các dòng hàng có thể giống hệt đơn cũ.

## 2. Ba khái niệm cần phân biệt

Trong thiết kế, thường gặp ba loại giá trị định danh:

**Entity identity (danh tính Entity)** là khái niệm domain dùng để phân biệt một Entity xuyên suốt vòng đời của nó trong phạm vi mô hình. Ví dụ, `OrderId` hoặc `CustomerId`.

**Business identifier (mã định danh nghiệp vụ)** là mã được nghiệp vụ hoặc người dùng sử dụng để tra cứu, trao đổi, in trên chứng từ hoặc tham chiếu theo quy trình. Ví dụ, `ORD-2026-00125`, mã khách hàng `CUS-0182`, mã hợp đồng `HD-2026-041`.

**Database primary key (khóa chính cơ sở dữ liệu)** là cột hoặc tập cột được database dùng để xác định duy nhất một hàng trong bảng. Ví dụ, cột `id BIGINT GENERATED ...` hoặc `id UUID PRIMARY KEY`.

Ba giá trị có thể trùng nhau hoặc được ánh xạ với nhau, nhưng không nhất thiết phải như vậy.

| Tiêu chí | Entity identity | Business identifier | Database primary key |
|---|---|---|---|
| Câu hỏi | Đây là Entity nào trong domain? | Người dùng/nghiệp vụ gọi hoặc tra cứu đối tượng bằng gì? | Hàng dữ liệu nào cần được tham chiếu? |
| Mục đích | Bảo toàn tính liên tục của Entity | Hỗ trợ quy trình, giao tiếp và tra cứu | Đảm bảo định danh hàng trong storage |
| Người quan tâm | Domain model và các hành vi liên quan | Chuyên gia nghiệp vụ, người dùng, hệ thống tích hợp | Database và persistence layer |
| Quy tắc | Ổn định trong vòng đời Entity theo mô hình | Có thể có định dạng, phạm vi và chính sách phát hành | Phải duy nhất trong phạm vi ràng buộc của bảng |
| Ví dụ | `OrderId` | `ORD-2026-00125` | `48291` |

Một hệ thống có thể dùng `OrderId` dạng UUID làm database primary key. Trong trường hợp đó, cùng một giá trị phục vụ hai vai trò. Tuy nhiên, domain vẫn quan tâm đến ý nghĩa `OrderId`, còn database quan tâm đến ràng buộc khóa chính. Nếu sau này database chuyển sang khóa số nội bộ, danh tính domain vẫn có thể được giữ nguyên thông qua ánh xạ.

## 3. Ví dụ: một đơn hàng có thể có nhiều mã

Giả sử khách đặt một đơn trên website. Hệ thống tạo các giá trị sau:

```text
Entity identity:
  OrderId = 7b82b5e0-3e8c-4d1c-9f01-6d2f0d0c6a21

Business identifier:
  OrderNumber = ORD-2026-00125

Database primary key:
  orders.id = 48291
```

`OrderId` giúp domain model và các thành phần nội bộ tham chiếu đúng Entity. `OrderNumber` được hiển thị trên trang xác nhận đơn, hóa đơn hoặc khi khách liên hệ hỗ trợ. `orders.id` có thể là khóa số do database tạo ra để tham chiếu nhanh trong bảng `orders`.

Một bảng dữ liệu minh họa:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id UUID NOT NULL UNIQUE,
    order_number VARCHAR(32) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

Trong thiết kế này:

- `id` là khóa chính kỹ thuật của hàng.
- `order_id` là giá trị danh tính mà domain sử dụng.
- `order_number` là mã nghiệp vụ có thể xuất hiện trên chứng từ và giao tiếp với khách.

Không phải hệ thống nào cũng cần ba cột. Nếu `order_id` chính là khóa chính UUID, có thể không cần `id` riêng. Nếu số đơn được thiết kế làm danh tính ổn định và đáp ứng các yêu cầu về duy nhất, nó có thể được dùng làm khóa domain. Điều quan trọng là quyết định phải xuất phát từ quy tắc domain và yêu cầu lưu trữ, không phải giả định rằng mọi loại mã đều giống nhau.

## 4. Business identifier có nhất thiết là danh tính Entity không?

Không. Một mã nghiệp vụ có thể dùng để tra cứu một Entity mà không phải là danh tính cốt lõi của Entity đó.

Ví dụ, số đơn `ORD-2026-00125` có thể được in trên chứng từ. Doanh nghiệp có thể thay đổi định dạng số đơn, thêm tiền tố theo chi nhánh hoặc chuyển sang cách cấp số mới. Nếu Order đã có một `OrderId` ổn định, thay đổi cách trình bày `OrderNumber` không cần làm Order trở thành một Entity khác.

Business identifier thường có những đặc điểm sau:

- Có ý nghĩa đối với người hoặc quy trình nghiệp vụ.
- Có định dạng dễ đọc hoặc theo quy ước của tổ chức.
- Có thể duy nhất trong một phạm vi, chẳng hạn theo chi nhánh, năm hoặc loại chứng từ.
- Có thể được cấp, điều chỉnh, ngừng sử dụng hoặc tái cấu trúc theo chính sách.
- Có thể không tồn tại ngay khi một Entity mới được tạo, tùy quy trình.

Business identifier có thể ổn định và duy nhất trong suốt vòng đời, nhưng không nên mặc định điều đó. Hãy hỏi chuyên gia nghiệp vụ: mã có được đổi không, có thể tái sử dụng không, phạm vi duy nhất là toàn hệ thống hay chỉ một đơn vị, và khi hợp nhất hai tổ chức thì xử lý trùng mã thế nào?

### Mã hiển thị và danh tính nội bộ

Một số mã được thiết kế để người dùng dễ đọc, ví dụ `INV-HCM-2026-00042`. Mã này có thể chứa thông tin chi nhánh và năm. Nếu doanh nghiệp chuyển chứng từ sang cách đánh số mới, việc giữ mã cũ để tra cứu lịch sử có thể quan trọng. Nhưng cấu trúc đó không nhất thiết là cách tốt nhất để làm primary key.

Hãy phân biệt yêu cầu “mã này phải được giữ nguyên trên hóa đơn đã phát hành” với yêu cầu “mã này là danh tính nội bộ của Entity”. Hai yêu cầu có thể cần các chính sách khác nhau.

## 5. Natural key và surrogate key

Khi thiết kế dữ liệu, có hai cách phổ biến để tạo khóa.

### Natural key (khóa tự nhiên)

Natural key sử dụng một hoặc nhiều thuộc tính vốn có ý nghĩa trong domain để nhận diện bản ghi. Ví dụ:

- Mã ISBN trong một hệ thống quản lý ấn bản sách.
- Mã quốc gia theo một tiêu chuẩn được xác định.
- Mã số hợp đồng nếu quy tắc nghiệp vụ đảm bảo nó duy nhất và ổn định trong phạm vi đã nêu.

Natural key có thể rất phù hợp nếu giá trị có ý nghĩa, được quản lý chặt chẽ và không thay đổi trong vòng đời liên quan. Tuy nhiên, nhiều thuộc tính trông có vẻ tự nhiên nhưng không ổn định hoặc không duy nhất.

Ví dụ, email có thể thay đổi, số điện thoại có thể được cấp lại cho người khác, tên công ty có thể đổi, địa chỉ có thể thay đổi. Những giá trị này thường là thuộc tính hoặc business identifier có chính sách riêng, không tự động trở thành danh tính Entity phù hợp.

### Surrogate key (khóa thay thế)

Surrogate key là giá trị được tạo ra chủ yếu để nhận diện bản ghi, không mang ý nghĩa nghiệp vụ trực tiếp. Ví dụ, một số tăng dần hoặc UUID.

Ưu điểm:

- Không phụ thuộc vào thuộc tính nghiệp vụ có thể thay đổi.
- Có thể tạo trước khi biết đầy đủ thông tin nghiệp vụ.
- Dễ tham chiếu từ các bảng và hệ thống liên quan.
- Hữu ích khi dữ liệu được hợp nhất từ nhiều nguồn có mã tự nhiên trùng nhau.

Nhược điểm:

- Không giúp người dùng hiểu hoặc tra cứu nghiệp vụ nếu đứng một mình.
- Vẫn cần quy tắc duy nhất cho business identifier khi nghiệp vụ yêu cầu.
- Có thể tạo thêm một lớp ánh xạ giữa mã nội bộ và mã nghiệp vụ.

### So sánh

| Tiêu chí | Natural key | Surrogate key |
|---|---|---|
| Nguồn tạo | Thuộc tính có ý nghĩa trong domain | Giá trị được tạo để định danh |
| Ý nghĩa nghiệp vụ | Thường có | Thường không |
| Khả năng thay đổi | Phụ thuộc quy tắc của thuộc tính | Thường ổn định hơn |
| Kích thước | Có thể dài hoặc gồm nhiều phần | Thường gọn và có định dạng cố định |
| Tích hợp dữ liệu | Có thể trùng giữa nguồn hoặc phạm vi | Cần chiến lược sinh và ánh xạ ID |
| Ví dụ | ISBN, mã hợp đồng | `BIGINT`, UUID, ULID |

Natural key không xấu và surrogate key không tự động tốt hơn trong mọi trường hợp. Hãy chọn dựa trên tính ổn định, quy tắc duy nhất, khả năng hợp nhất và cách nghiệp vụ sử dụng mã.

## 6. Composite key và phạm vi duy nhất

Một định danh có thể gồm nhiều thành phần. Ví dụ, số thứ tự dòng hàng chỉ duy nhất bên trong một Order. Khi đó, cặp `(order_id, line_number)` có thể nhận diện một Order Line trong phạm vi Order.

```text
Order ORD-2026-00125
  Line 1: SKU-BOOK-01
  Line 2: SKU-BAG-03

Order ORD-2026-00126
  Line 1: SKU-BOOK-01
```

`line_number = 1` xuất hiện ở cả hai Order nhưng không gây trùng nếu phạm vi duy nhất là từng Order. Một khóa tổng hợp có thể được biểu diễn là `(orderId, lineNumber)`.

Ví dụ ràng buộc database:

```sql
CREATE TABLE order_lines (
    order_id UUID NOT NULL,
    line_number INTEGER NOT NULL,
    sku VARCHAR(64) NOT NULL,
    quantity INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_number)
);
```

Composite key hữu ích khi danh tính thực sự phụ thuộc vào một phạm vi cha hoặc nhiều thành phần. Tuy nhiên, nếu các thành phần có thể thay đổi, hoặc cần tham chiếu Order Line từ nhiều nơi, một `OrderLineId` riêng có thể đơn giản hơn. Cũng có thể dùng surrogate primary key và giữ unique constraint trên `(order_id, line_number)`.

Điều cần làm rõ là:

- Mã có duy nhất toàn hệ thống hay chỉ trong một context, tenant, chi nhánh hoặc đối tượng cha?
- Hai bản ghi có thể dùng cùng mã ở hai phạm vi khác nhau không?
- Khi chuyển bản ghi sang phạm vi khác, danh tính có thay đổi không?
- Có cần một mã toàn cục để tích hợp không?

## 7. Danh tính trong Entity và Value Object

Entity và Value Object được phân biệt chủ yếu bởi cách xác định sự đồng nhất.

**Entity** được so sánh dựa trên danh tính. Hai Entity có cùng các thuộc tính hiện tại vẫn có thể là hai đối tượng khác nhau nếu ID khác nhau.

**Value Object** được so sánh dựa trên giá trị cấu thành. Ví dụ, hai `Money(100000, VND)` có thể được xem là bằng nhau nếu cùng currency và amount theo quy tắc domain. Value Object thường không cần ID riêng.

| Ví dụ | Loại mô hình | Cách xác định bằng nhau |
|---|---|---|
| `Order` | Entity | Cùng `OrderId` trong Sales Context |
| `Customer` | Entity | Cùng `CustomerId` trong Customer Context |
| `Money` | Value Object | Cùng số tiền và currency theo quy tắc so sánh |
| `Address` | Thường là Value Object | Cùng các thành phần địa chỉ có ý nghĩa |
| `OrderLine` | Entity hoặc phần tử có identity trong Aggregate tùy domain | Theo ID riêng hoặc identity trong phạm vi Order nếu domain cần phân biệt vòng đời |

Một địa chỉ có thể được gắn với Customer nhưng không nhất thiết là Entity. Nếu địa chỉ chỉ là tập giá trị được thay thế khi khách cập nhật hồ sơ, Value Object là phù hợp. Nếu doanh nghiệp quản lý một điểm giao hàng có lịch sử, quyền sở hữu, trạng thái và tham chiếu độc lập, nó có thể cần danh tính riêng. Cần nhìn vào domain thay vì quyết định dựa trên việc dữ liệu có một cột `id`.

## 8. Entity identity phải ổn định qua thay đổi thuộc tính

Một nguyên tắc quan trọng là thay đổi thuộc tính mô tả không làm thay đổi danh tính Entity.

Ví dụ với Customer:

```text
CustomerId: CUS-0182
Name: Nguyễn An
Email: an@example.test
Phone: 0900...
```

Sau đó khách đổi email:

```text
CustomerId: CUS-0182
Name: Nguyễn An
Email: an.new@example.test
Phone: 0900...
```

Đây vẫn là cùng một Customer vì `CustomerId` không đổi. Nếu dùng email làm identity, hệ thống có thể xem đây là một khách hàng mới hoặc buộc phải cập nhật mọi tham chiếu đến khách hàng khi email thay đổi.

Các thuộc tính thường không nên dùng làm identity nếu chúng có thể thay đổi trong vòng đời:

- Tên người hoặc tên tổ chức.
- Email, số điện thoại.
- Địa chỉ.
- Trạng thái, hạng thành viên hoặc nhóm phân loại.
- Giá, mô tả hoặc thuộc tính sản phẩm.

Một thuộc tính có thể được bảo đảm duy nhất tại một thời điểm nhưng vẫn không phải identity ổn định. Ví dụ, email có unique constraint vẫn có thể thay đổi; unique constraint ngăn trùng đồng thời, không chứng minh giá trị đó bất biến suốt vòng đời Entity.

## 9. Identity trong Bounded Context có phạm vi riêng

Danh tính Entity có ý nghĩa trong một mô hình và Bounded Context. Cùng một người hoặc một sản phẩm ngoài đời có thể được các context biểu diễn bằng các Entity và ID khác nhau.

Ví dụ:

| Context | Entity | ID | Mục đích |
|---|---|---|---|
| Customer | Customer | `CustomerId` | Quản lý quan hệ khách hàng |
| Sales | BuyerAccount | `BuyerId` | Ghi nhận bên mua và quyền mua |
| Payment | PayerProfile | `PayerId` | Quản lý hồ sơ thanh toán |
| Fulfillment | Recipient | `RecipientId` | Xác định người nhận hàng |

Trong một giao dịch mua quà, người mua, người trả tiền và người nhận có thể là ba người khác nhau. Không nên ép mọi context dùng chung một `CustomerId` nếu các khái niệm và trách nhiệm khác nhau.

Khi các context cần liên hệ dữ liệu, chúng có thể trao đổi qua các identifier hoặc contract đã thống nhất. Ví dụ Sales gửi `orderId`, `buyerReference` và `recipientDetailsSnapshot` cho Fulfillment. Payment nhận `orderId` cùng thông tin nghĩa vụ thanh toán. Mỗi context chuyển đổi dữ liệu sang mô hình nội bộ của mình.

### Không nên giả định ID có ý nghĩa toàn cục

Một `CustomerId` chỉ có thể duy nhất trong một tenant hoặc một hệ thống nguồn. Khi hợp nhất dữ liệu từ nhiều tổ chức, `CUS-001` có thể xuất hiện nhiều lần. Cần xác định namespace hoặc định danh nguồn, ví dụ `(sourceSystem, customerId)`, hay cấp một ID toàn cục mới và lưu mapping.

UUID làm giảm nguy cơ trùng khi sinh phân tán, nhưng không tự giải quyết bài toán nhận diện cùng một người ở hai hệ thống. Hai hệ thống có thể cấp hai UUID khác nhau cho cùng một con người. Việc liên kết danh tính là một quy tắc nghiệp vụ và dữ liệu riêng, không chỉ là chọn định dạng ID.

## 10. Chọn cách sinh ID

Có nhiều cách tạo ID cho Entity. Mỗi cách có ưu và nhược điểm.

### Sequence hoặc số tăng dần

Database hoặc một dịch vụ cấp số tạo giá trị tăng dần như `48291`.

Ưu điểm:

- Gọn và dễ đọc trong log hoặc công cụ quản trị.
- Có thể đánh index hiệu quả trong nhiều hệ quản trị dữ liệu.
- Dễ triển khai khi một database hoặc sequence service chịu trách nhiệm cấp số.

Hạn chế:

- Có thể làm lộ số lượng hoặc thứ tự tạo bản ghi nếu công khai trực tiếp.
- Khó tạo độc lập ở nhiều node nếu không có cơ chế phân phối.
- Thường gắn với hạ tầng cấp số.
- Không nên dùng số tăng dần làm mã nghiệp vụ nếu nghiệp vụ cần quy tắc phát hành riêng.

### UUID

UUID là mã định danh có kích thước cố định, được thiết kế để giảm khả năng trùng khi tạo phân tán. UUID có thể được sinh trong ứng dụng trước khi lưu database.

Ưu điểm:

- Có thể tạo trước khi persist.
- Phù hợp với hệ thống nhiều node hoặc cần tạo ID offline.
- Không phụ thuộc vào sequence trung tâm.

Hạn chế:

- Dài và khó đọc bằng mắt.
- Một số phiên bản có đặc tính phân bố index khác nhau; cần chọn theo database và workload.
- UUID không thay thế business identifier dễ đọc.

### ULID hoặc định danh có thứ tự thời gian

ULID và một số định dạng tương tự tạo ID có phần thời gian để thuận tiện sắp xếp gần theo thời điểm tạo. Chúng có thể phù hợp với hệ thống cần sinh phân tán và thứ tự gần đúng.

Tuy nhiên, thứ tự mã không phải lúc nào cũng là thứ tự nghiệp vụ. Đồng hồ máy có thể lệch, nhiều sự kiện có thể xảy ra đồng thời và một giao dịch có thể được ghi nhận muộn. Không dùng thứ tự ID để thay thế quy tắc thời gian domain nếu thứ tự có ý nghĩa.

### ID do domain tạo hay database tạo?

Nếu Entity cần được tham chiếu trước khi lưu, hoặc cần tạo event có ID ngay trong quá trình xử lý, sinh ID ở application/domain boundary có thể thuận tiện. Nếu database cấp khóa kỹ thuật, persistence layer có thể tạo khóa sau khi insert và ánh xạ lại.

Không có lựa chọn duy nhất đúng cho mọi hệ thống. Hãy xem xét:

- Entity cần ID tại thời điểm nào?
- Có tạo Entity khi chưa kết nối database không?
- Có nhiều node cùng tạo Entity không?
- ID có xuất hiện trong event hoặc contract tích hợp không?
- Có yêu cầu bảo mật hoặc không muốn lộ thứ tự tạo không?
- Cách sinh ID có làm domain phụ thuộc vào database không?

## 11. Biểu diễn ID bằng kiểu riêng trong domain model

Trong code, dùng `UUID` hoặc `Long` trực tiếp ở mọi nơi có thể khiến nhầm lẫn giữa các loại ID. Ví dụ, một phương thức nhận hai tham số `UUID` có thể vô tình truyền `customerId` vào vị trí `orderId` mà compiler không phát hiện.

Có thể dùng Value Object cho từng loại ID:

```java
import java.util.UUID;

public record OrderId(UUID value) {
    public OrderId {
        if (value == null) {
            throw new IllegalArgumentException("OrderId is required");
        }
    }

    public static OrderId newId() {
        return new OrderId(UUID.randomUUID());
    }
}

public record CustomerId(UUID value) {
    public CustomerId {
        if (value == null) {
            throw new IllegalArgumentException("CustomerId is required");
        }
    }
}
```

Khi đó, chữ ký phương thức diễn đạt rõ hơn:

```java
public Order loadOrder(OrderId orderId) { ... }

public Customer loadCustomer(CustomerId customerId) { ... }
```

`OrderId` và `CustomerId` có thể cùng bao một UUID, nhưng là hai kiểu khác nhau. Compiler giúp ngăn việc truyền nhầm loại ID.

Nếu cần business identifier, có thể định nghĩa một kiểu riêng:

```java
public record OrderNumber(String value) {
    public OrderNumber {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("OrderNumber is required");
        }
    }
}
```

Domain model có thể giữ cả `OrderId` và `OrderNumber` nếu cả hai có ý nghĩa. Quy tắc định dạng và phát hành `OrderNumber` nên được đặt ở nơi sở hữu chính sách cấp số, chẳng hạn một domain service hoặc application service phối hợp với một sequence provider. Không nên để mọi nơi tự ghép chuỗi theo cách riêng.

## 12. So sánh Entity theo identity

Vì Entity được xác định bằng identity, hai instance đại diện cho cùng một Entity có thể bằng nhau dù các thuộc tính khác nhau.

Ví dụ:

```text
Instance A:
  OrderId = O-100
  Status = Pending

Instance B:
  OrderId = O-100
  Status = Confirmed
```

Nếu hai instance là hai lần nạp hoặc hai biểu diễn của cùng Order trong cùng context, chúng có cùng identity dù trạng thái khác nhau. Ngược lại:

```text
Instance C:
  OrderId = O-101
  Status = Pending
```

Instance C là một Order khác dù mọi thuộc tính còn lại giống A.

Một quy tắc so sánh thường dùng là cùng loại Entity và cùng ID trong phạm vi identity đã xác định. Tuy nhiên, cần chú ý vòng đời của Entity mới chưa có ID, proxy ORM và các quy tắc equality của ngôn ngữ/framework.

### Entity mới chưa có ID

Nếu ID được database cấp sau khi insert, hai object mới chưa persist có thể cùng `id = null`. Không được xem chúng là cùng một Entity chỉ vì cả hai chưa có ID. Có thể:

- cấp ID trước khi persist,
- dùng identity tạm thời trong memory,
- hoặc định nghĩa equality có xử lý riêng cho transient instance.

Trong DDD, việc cấp ID sớm thường giúp Entity có danh tính ngay từ khi được tạo. Dù vậy, đây là quyết định thiết kế, không phải yêu cầu bắt buộc của mọi persistence framework.

### Không so sánh Entity bằng toàn bộ thuộc tính

Nếu `equals()` so sánh mọi field, một Entity có thể trở nên “khác” chỉ vì tên hoặc trạng thái đổi. Điều đó trái với ý nghĩa identity. Với Entity, cần xác định rõ ID nào quyết định equality; với Value Object, so sánh theo giá trị cấu thành.

## 13. Persistence model có thể dùng khóa khác domain identity

Domain model và persistence model có mục tiêu khác nhau. Domain model diễn đạt ý nghĩa và hành vi; persistence model tổ chức dữ liệu để lưu và truy vấn. Chúng có thể dùng cùng một ID hoặc ánh xạ giữa các loại ID.

Ví dụ domain:

```java
public class Order {
    private final OrderId id;
    private final OrderNumber number;
    private OrderStatus status;

    public Order(OrderId id, OrderNumber number) {
        this.id = id;
        this.number = number;
        this.status = OrderStatus.DRAFT;
    }

    public OrderId id() {
        return id;
    }

    public OrderNumber number() {
        return number;
    }
}
```

Persistence record có thể có cấu trúc khác:

```java
public class OrderRow {
    private Long id;             // Khóa chính kỹ thuật
    private UUID orderId;        // Domain identity
    private String orderNumber;  // Mã nghiệp vụ
    private String status;
}
```

Repository hoặc mapper chuyển đổi giữa `Order` và `OrderRow`. Domain không cần biết `OrderRow.id` được cấp bằng sequence như thế nào. Nếu dùng JPA, có thể ánh xạ các field này bằng annotation hoặc persistence adapter riêng; không cần đưa annotation persistence vào domain model nếu kiến trúc đang tách hai lớp.

### Khi nào dùng cùng một khóa?

Có thể dùng domain identity làm primary key khi:

- ID được tạo và quản lý phù hợp với vòng đời Entity.
- Kiểu và kích thước khóa đáp ứng yêu cầu storage.
- Không cần một khóa nội bộ khác cho persistence hoặc tích hợp.
- Quyết định không làm domain phụ thuộc không cần thiết vào database.

Có thể dùng khóa kỹ thuật riêng khi:

- Database hoặc ORM có lý do cụ thể để dùng surrogate key.
- Dữ liệu được hợp nhất từ nhiều nguồn với identity khác nhau.
- Cần giữ business ID hoặc domain ID độc lập với cách lưu trữ.
- Có yêu cầu di chuyển, đồng bộ hoặc mapping nhiều hệ thống.

Điều cần tránh là để khóa kỹ thuật rò vào giao diện nghiệp vụ chỉ vì nó tiện lấy từ ORM.

## 14. Identity và Repository

Repository cung cấp cách truy xuất Entity theo ngôn ngữ domain. Một repository thường có phương thức nhận ID của Entity thay vì bắt caller hiểu cấu trúc bảng.

Ví dụ:

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId orderId);
    Optional<Order> findByNumber(OrderNumber orderNumber);
    void save(Order order);
}
```

`findById` truy xuất theo danh tính domain. `findByNumber` truy xuất theo mã nghiệp vụ nếu use case cần tra cứu theo số đơn. Cả hai phương thức đều trả về Order, nhưng phục vụ các cách tìm khác nhau.

Implementation có thể dùng `order_id` hoặc `order_number` để truy vấn. Nếu database có `id` nội bộ riêng, repository/mapper sẽ xử lý việc ánh xạ. Caller không cần biết bảng có cột nào làm primary key.

Không nên đặt tên repository như `findByDatabaseRowId` trong domain interface trừ khi khái niệm đó thực sự thuộc domain. Persistence adapter có thể biết khóa storage; domain API nên nói bằng ngôn ngữ của Entity.

## 15. Business identifier trong API và tích hợp

Khi thiết kế API, cần xác định người gọi đang truyền loại ID nào và phạm vi của nó.

Ví dụ:

```http
GET /orders/ORD-2026-00125
```

Endpoint có thể dùng số đơn vì đây là mã mà khách hàng và nhân viên biết. API sẽ tìm Order theo `OrderNumber`.

Một API nội bộ khác có thể dùng UUID:

```http
GET /internal/orders/7b82b5e0-3e8c-4d1c-9f01-6d2f0d0c6a21
```

Hai endpoint có thể trả cùng một tài nguyên. Điều quan trọng là contract phải nêu rõ identifier nào được nhận, phạm vi duy nhất và cách xử lý khi không tìm thấy hoặc mã không hợp lệ.

### Tránh lộ khóa kỹ thuật một cách vô tình

Nếu API trả `orders.id = 48291`, client có thể bắt đầu lưu và sử dụng giá trị này như business identifier. Sau này khi chuyển database hoặc đổi chiến lược khóa, việc thay đổi có thể phá vỡ nhiều client.

Điều này không có nghĩa mọi API đều phải dùng UUID. Một số hệ thống có thể công khai khóa số một cách có chủ đích. Hãy đánh giá yêu cầu bảo mật, khả năng đoán ID, tính ổn định của contract và nhu cầu tra cứu nghiệp vụ trước khi quyết định.

### Phân biệt ID nội bộ với mã của hệ thống bên ngoài

Khi tích hợp đối tác, hệ thống có thể cần lưu `externalOrderId` hoặc `providerReference`. Đây là mã do hệ thống ngoài cấp, không tự động trở thành identity của Order nội bộ.

Một mapping có thể gồm:

```text
OrderId:              7b82...
OrderNumber:          ORD-2026-00125
PaymentProviderRef:   pay_8JH...
ShippingProviderRef:  ship_73K...
```

Mỗi mã thuộc một namespace và có owner khác nhau. Không nên giả định `providerReference` luôn duy nhất toàn hệ thống nếu nhà cung cấp chỉ đảm bảo duy nhất trong tài khoản merchant hoặc trong một khoảng thời gian.

## 16. Những rủi ro khi dùng thuộc tính cá nhân làm identity

Email, số điện thoại, số giấy tờ hoặc các thuộc tính cá nhân có thể được dùng để tìm kiếm, xác minh hoặc đối chiếu một người. Nhưng chúng thường có quy tắc về thay đổi, bảo mật, quyền riêng tư và phạm vi sử dụng riêng.

Không nên chọn một thuộc tính nhạy cảm làm khóa công khai chỉ vì nó có vẻ duy nhất. Giá trị đó có thể thay đổi, bị cấp lại, bị lộ hoặc không được phép dùng làm định danh trong một số quy trình. Hãy dùng một ID nội bộ phù hợp và kiểm soát cách lưu, hiển thị, tìm kiếm các thuộc tính cá nhân theo yêu cầu nghiệp vụ và bảo vệ dữ liệu.

Ví dụ, `CustomerId` có thể là UUID nội bộ; email là thuộc tính có thể thay đổi và có thể có unique constraint theo policy; số giấy tờ được lưu theo quy tắc truy cập riêng. Ba giá trị không nên bị gộp thành một khái niệm identity.

## 17. Quy trình lựa chọn định danh cho một Entity

Khi mô hình hóa một Entity mới, có thể đi qua các bước sau:

**Bước 1: Xác định Entity trong ngữ cảnh.** Mô tả đối tượng, vòng đời và trách nhiệm nghiệp vụ của nó. Ví dụ, Order trong Sales là cam kết mua bán được chấp nhận theo chính sách bán hàng.

**Bước 2: Hỏi cách nhận diện qua thời gian.** Nếu tên, trạng thái, địa chỉ hoặc giá thay đổi, làm sao biết vẫn là cùng một Entity?

**Bước 3: Thu thập các mã đang được sử dụng.** Có mã nội bộ, số chứng từ, mã từ hệ thống ngoài hay khóa database nào? Ai cấp và ai sở hữu từng mã?

**Bước 4: Xác định quy tắc duy nhất và phạm vi.** Mã duy nhất toàn tổ chức, theo tenant, theo năm, theo chi nhánh hay theo Entity cha?

**Bước 5: Kiểm tra tính ổn định.** Mã có thể thay đổi, tái sử dụng, cấp lại hoặc bị ảnh hưởng khi hợp nhất dữ liệu không?

**Bước 6: Chọn domain identity.** Dùng một kiểu ID rõ nghĩa, ổn định và phù hợp với cách tạo Entity. Nếu business identifier đáp ứng đầy đủ yêu cầu, có thể cân nhắc dùng nó làm domain identity; nếu không, tạo ID riêng.

**Bước 7: Chọn primary key cho persistence.** Có thể dùng cùng giá trị với domain ID hoặc dùng surrogate key riêng. Giữ unique constraint phù hợp cho các mã nghiệp vụ.

**Bước 8: Định nghĩa equality và repository.** Entity được so sánh theo identity nào? Repository truy xuất theo domain ID hay cần thêm cách tra cứu bằng business identifier?

**Bước 9: Xác định contract tích hợp.** Mã nào được gửi ra ngoài? Namespace và owner của nó là gì? Context nhận cần mapping nào?

## 18. Bảng câu hỏi để kiểm tra một lựa chọn ID

| Câu hỏi | Điều cần xác nhận |
|---|---|
| Giá trị này có phân biệt được hai Entity cùng loại không? | Quy tắc duy nhất và phạm vi áp dụng |
| Giá trị có thay đổi trong vòng đời không? | Chính sách thay đổi hoặc giữ ổn định |
| Ai tạo và quản lý giá trị? | Domain, ứng dụng, database hay hệ thống ngoài |
| Người dùng nghiệp vụ có cần đọc hoặc trao đổi mã này không? | Có cần business identifier riêng |
| Mã có thể trùng giữa tenant hoặc nguồn dữ liệu không? | Namespace và chiến lược mapping |
| Entity cần được tham chiếu trước khi lưu không? | Thời điểm sinh ID |
| Có cần hợp nhất dữ liệu từ nhiều hệ thống không? | Surrogate/domain ID và bảng ánh xạ |
| Mã có chứa dữ liệu nhạy cảm hoặc tiết lộ thứ tự không? | Cách công khai và bảo vệ ID |
| Persistence có cần khóa riêng không? | Mapping domain ID và primary key |

Không có một định dạng ID phù hợp với mọi Entity. Một lựa chọn tốt phải trả lời được các câu hỏi này bằng quy tắc rõ ràng.

## 19. Những sai lầm thường gặp

**Dùng tên làm identity.** Tên có thể trùng hoặc đổi. Hãy dùng một danh tính ổn định và giữ tên như thuộc tính mô tả.

**Dùng email hoặc số điện thoại làm identity mà không xét vòng đời.** Những giá trị này có thể đổi hoặc được tái sử dụng. Hãy xác định rõ chúng là identifier tra cứu hay identity thực sự.

**Dùng khóa tăng dần của database làm mã nghiệp vụ.** Điều này có thể làm lộ thứ tự tạo và khiến API phụ thuộc vào storage. Chỉ công khai khi đó là quyết định có chủ đích.

**Cho rằng UUID tự giải quyết mọi vấn đề identity.** UUID giảm nguy cơ trùng khi tạo phân tán, nhưng không chứng minh hai bản ghi từ hai hệ thống là cùng một người hoặc cùng một sản phẩm.

**Giả định business identifier luôn duy nhất toàn cục.** Mã có thể chỉ duy nhất theo tenant, chi nhánh, năm hoặc loại chứng từ. Hãy ghi rõ phạm vi.

**So sánh Entity bằng toàn bộ field.** Một thay đổi trạng thái hoặc địa chỉ không nên biến Entity thành đối tượng khác. Equality cần dựa trên identity theo mô hình.

**Để persistence key rò vào domain interface.** Domain nên dùng `OrderId`; repository adapter chịu trách nhiệm chuyển đổi sang khóa kỹ thuật nếu có.

**Dùng chung ID giữa các Bounded Context mà không có lý do.** Các context có thể có identity riêng cho những khái niệm khác nhau. Hãy trao đổi qua contract và mapping có ý nghĩa.

## 20. Bài tập tự kiểm tra

Một nền tảng cho thuê xe quản lý một chiếc xe với các thông tin:

```text
Database id:  12045
VehicleId:    9f2c6b8d-...
LicensePlate: 51A-123.45
FleetCode:    HCM-CAR-0082
ProviderRef:  EXT-VEH-771
```

Hãy trả lời:

1. Giá trị nào là khóa chính kỹ thuật, giá trị nào là domain identity và giá trị nào là business identifier?
2. Nếu xe đổi biển số sau khi đăng ký lại, Entity có còn là cùng một xe không? Vì sao?
3. Nếu xe được chuyển từ chi nhánh HCM sang chi nhánh khác và `FleetCode` thay đổi, identity có nên đổi không?
4. Nếu hệ thống đối tác cũng có một `VehicleId` dạng UUID, có thể giả định nó trùng với `VehicleId` nội bộ không?
5. Khi hai công ty hợp nhất dữ liệu và cùng có `FleetCode = CAR-0082`, cần thêm thông tin nào để phân biệt?
6. Nếu API cho thuê xe nhận `LicensePlate` làm đường dẫn, những rủi ro nào cần xem xét?

Gợi ý:

| Giá trị | Vai trò có thể có | Lưu ý |
|---|---|---|
| `12045` | Database primary key | Có thể chỉ phục vụ persistence |
| `9f2c6b8d-...` | Domain identity | Duy trì khi xe đổi biển số hoặc chi nhánh nếu vẫn là cùng Entity |
| `51A-123.45` | Mã đăng ký/biển số nghiệp vụ | Có thể thay đổi khi đăng ký lại và có quy tắc pháp lý riêng |
| `HCM-CAR-0082` | Business identifier nội bộ | Phạm vi có thể phụ thuộc chi nhánh hoặc đội xe |
| `EXT-VEH-771` | Identifier của đối tác | Cần namespace và mapping đến Vehicle nội bộ |

Đây là cách phân loại minh họa. Doanh nghiệp cần xác nhận liệu `FleetCode` có phải identity theo quy trình của họ hay chỉ là mã quản lý. Nếu xe được bán và thay thế bằng xe khác có cùng biển số hoặc mã đội xe, đó có thể là hai Entity khác nhau dù một số thuộc tính giống nhau.

## Kết luận

Danh tính Entity là khái niệm domain giúp nhận diện cùng một đối tượng xuyên suốt vòng đời, ngay cả khi trạng thái và thuộc tính thay đổi. Business identifier giúp con người và quy trình tra cứu, trao đổi về đối tượng. Database primary key giúp database xác định hàng dữ liệu. Ba vai trò có thể dùng chung một giá trị, nhưng cần được phân biệt về ý nghĩa và trách nhiệm.

Khi thiết kế, hãy kiểm tra tính duy nhất, phạm vi, độ ổn định, owner và cách sử dụng của từng mã. Chọn domain identity phù hợp với vòng đời Entity, giữ business identifier theo chính sách nghiệp vụ và để persistence layer quyết định cách lưu trữ. Cách phân biệt này giúp mô hình domain ít phụ thuộc vào database, đồng thời hỗ trợ tích hợp và thay đổi hệ thống an toàn hơn.
