# Ngữ cảnh giới hạn và phạm vi nhất quán của một mô hình

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích **ngữ cảnh giới hạn** (*bounded context*) và vì sao một thuật ngữ nghiệp vụ có thể mang nhiều nghĩa hợp lệ trong cùng hệ thống.
- Phân biệt **ranh giới nhất quán về ngữ nghĩa** của mô hình, **ranh giới nhất quán giao dịch** của aggregate và **ranh giới lưu trữ vật lý**.
- Tách một miền nghiệp vụ thành các mô hình có trách nhiệm và nguồn dữ liệu rõ ràng; xác định ràng buộc nào phải đúng ngay lập tức, ràng buộc nào được đồng bộ theo thời gian.
- Chuyển các ranh giới đó thành lược đồ, khóa, quan hệ, quy tắc cập nhật và hợp đồng tích hợp có thể kiểm chứng.

Trong thiết kế dữ liệu, việc tìm đủ thực thể, thuộc tính và khóa mới giải quyết một phần bài toán. Nếu đặt mọi thông tin mang tên "Sản phẩm", "Khách hàng" hay "Đơn hàng" vào một mô hình dùng chung, ta dễ tạo ra lược đồ khó thay đổi: nhóm bán hàng muốn lưu giá lúc đặt mua, nhóm danh mục muốn cập nhật giá hiện hành, còn kho muốn quản lý lượng hàng khả dụng. Các yêu cầu này liên quan đến cùng mã sản phẩm nhưng **không đòi hỏi cùng một đối tượng dữ liệu hoặc cùng một quy tắc nhất quán**.

## 1. Ngữ cảnh giới hạn là gì?

Trong Domain-Driven Design (DDD), **bounded context** là phạm vi mà một mô hình miền và ngôn ngữ nghiệp vụ của nó được định nghĩa một cách nhất quán. Bên trong phạm vi ấy, các thuật ngữ, quy tắc và ý nghĩa của dữ liệu phải rõ ràng với những người sử dụng mô hình. Bên ngoài phạm vi ấy, một nhóm khác có thể có mô hình khác cho cùng một sự vật ngoài đời.

Ví dụ, khi khách hàng mua một chiếc laptop:

| Ngữ cảnh | "Sản phẩm" có ý nghĩa gì? | Dữ liệu cần quản lý |
| --- | --- | --- |
| Danh mục (Catalog) | Mặt hàng đang được giới thiệu để bán | Tên, mô tả, danh mục, giá niêm yết hiện tại |
| Bán hàng (Sales) | Mặt hàng đã được chọn tại thời điểm đặt đơn | Mã tham chiếu, tên và đơn giá tại lúc mua, số lượng |
| Tồn kho (Inventory) | Đơn vị hàng có thể nhập, xuất, giữ chỗ | SKU, kho, số lượng khả dụng, lượng đã giữ |

Giá niêm yết ngày hôm nay trong Catalog có thể là 24 triệu đồng, nhưng dòng hàng trong đơn đã xác nhận hôm qua vẫn phải giữ đơn giá 23 triệu đồng theo giao dịch đã diễn ra. Hai giá trị khác nhau **không phải lỗi đồng bộ**: mỗi giá trị trả lời một câu hỏi nghiệp vụ khác nhau.

Khái niệm cốt lõi:

- **Miền nghiệp vụ (domain):** toàn bộ lĩnh vực mà phần mềm hỗ trợ, ví dụ bán hàng trực tuyến.
- **Miền con (subdomain):** một nhóm năng lực nghiệp vụ, ví dụ quản lý đơn hay quản lý tồn kho.
- **Ngữ cảnh giới hạn (bounded context):** nơi một mô hình cụ thể có hiệu lực, có ngôn ngữ và quy tắc riêng. Một miền con có thể chứa nhiều ngữ cảnh; hai khái niệm không đồng nghĩa.
- **Mô hình miền (domain model):** các khái niệm, quan hệ, trạng thái, hành vi và bất biến để diễn đạt nghiệp vụ trong ngữ cảnh đó. Mô hình không chỉ là danh sách bảng cơ sở dữ liệu.
- **Ngôn ngữ chung (ubiquitous language):** cách dùng thuật ngữ được thống nhất giữa người làm nghiệp vụ và người phát triển **trong cùng ngữ cảnh**.

Tên gọi giống nhau không bắt buộc cấu trúc giống nhau. Ngược lại, cùng một mã nhận dạng bên ngoài có thể được giữ ở nhiều ngữ cảnh để đối chiếu mà không khiến các mô hình trở thành một.

## 2. Ba loại ranh giới cần tách bạch

Cụm từ "phạm vi nhất quán của một mô hình" thường bị hiểu lẫn với phạm vi của một giao dịch ACID. Để chọn cấu trúc dữ liệu chính xác, cần xác định ba lớp:

| Lớp | Câu hỏi thiết kế | Ví dụ | Điều **không** được suy ra |
| --- | --- | --- | --- |
| **Ngữ nghĩa – bounded context** | Các thuật ngữ và quy tắc nào cùng thuộc một mô hình? | Trong Sales, "đơn đã xác nhận" có nghĩa xác định | Không có nghĩa mọi thay đổi trong Sales phải nằm trong một giao dịch duy nhất |
| **Bất biến/giao dịch – aggregate** | Những dữ liệu nào phải thay đổi cùng nhau để một quy tắc luôn đúng sau mỗi thao tác? | Đơn hàng và các dòng hàng; không cho số lượng dòng hàng âm hoặc bằng 0 | Không có nghĩa cả ngữ cảnh Sales chỉ có một aggregate |
| **Vật lý – database/schema/service** | Lưu và triển khai các mô hình ở đâu? | Schema sales và catalog cùng nằm trong PostgreSQL | Không tự động chứng minh hai schema là hai bounded context độc lập |

**Bất biến (invariant)** là điều kiện phải luôn đúng ở các trạng thái hợp lệ của một đối tượng hoặc aggregate, ví dụ mỗi dòng đơn có số lượng lớn hơn 0 và đơn đã xác nhận không được sửa giá mua. **Aggregate** là cụm đối tượng có một gốc (*aggregate root*) điều phối thay đổi, thường được thiết kế như ranh giới nhất quán giao dịch. Đây là nguyên tắc thiết kế, không phải đặc tính tự động có được chỉ bằng cách tạo bảng và khóa ngoại.

Một bounded context có thể chứa nhiều aggregate; một service có thể triển khai nhiều bounded context; một bounded context cũng có thể trải qua nhiều thành phần triển khai. Chọn kiến trúc triển khai sau khi đã hiểu ranh giới nghiệp vụ, tránh dùng số lượng bảng, repository hoặc microservice làm tiêu chí chia ngữ cảnh.

## 3. Phân định mô hình qua một quy trình bán hàng

Xét luồng khách mua hàng, hệ thống có bốn ngữ cảnh:

1. **Catalog** sở hữu thông tin trình bày mặt hàng và giá đang công bố.
2. **Sales** sở hữu đơn hàng, dòng hàng, giá đã chốt và trạng thái xử lý đơn.
3. **Inventory** sở hữu lượng tồn, đặt giữ hàng và giải phóng hàng đã giữ.
4. **Payment** sở hữu yêu cầu thanh toán, kết quả ủy quyền hoặc thu tiền và mã giao dịch của nhà cung cấp thanh toán.

~~~mermaid
flowchart LR
    C["Catalog<br/>Thông tin mặt hàng hiện tại"]
    S["Sales<br/>Đơn hàng và giá đã chốt"]
    I["Inventory<br/>Tồn kho và giữ hàng"]
    P["Payment<br/>Giao dịch thanh toán"]

    C -->|"Thông tin mặt hàng / giá đề xuất"| S
    S -->|"Yêu cầu giữ hàng"| I
    I -->|"Kết quả giữ hàng"| S
    S -->|"Yêu cầu thanh toán"| P
    P -->|"Kết quả thanh toán"| S
~~~

Các mũi tên biểu diễn **hợp đồng trao đổi thông tin**, không có nghĩa các ngữ cảnh dùng chung một bảng hoặc luôn gọi nhau đồng bộ. Có thể triển khai bằng API, sự kiện hoặc phối hợp cả hai.

Xác định dữ liệu gốc và bản sao theo mục đích:

| Dữ liệu | Bên có quyền quyết định giá trị | Bên tiêu thụ và cách sử dụng |
| --- | --- | --- |
| Tên/mô tả/giá công bố hiện tại | Catalog | Sales đọc để hiển thị và lập đơn nháp |
| Đơn giá đã chấp nhận khi đặt đơn | Sales | Sales lưu bản chụp (*snapshot*) để bảo toàn lịch sử giao dịch |
| Số lượng khả dụng và phiếu giữ hàng | Inventory | Sales nhận kết quả giữ hàng, không tự trừ tồn trong bảng đơn |
| Trạng thái giao dịch với cổng thanh toán | Payment | Sales nhận kết quả để quyết định trạng thái đơn |

Một mã như "productId" trong dòng đơn là **tham chiếu tới khái niệm bên ngoài**. Nó không khiến Sales có quyền sửa Catalog. Khi hai ngữ cảnh dùng chung một cơ sở dữ liệu, việc gắn khóa ngoại trực tiếp xuyên ranh giới có thể tạo phụ thuộc vòng đời, triển khai và xóa dữ liệu; hãy cân nhắc hợp đồng tích hợp, khóa tham chiếu nghiệp vụ và kiểm tra tính tồn tại tại thời điểm nhận dữ liệu. Khóa ngoại **bên trong** mỗi ngữ cảnh vẫn rất hữu ích.

## 4. Tìm đúng phạm vi giao dịch cho các bất biến

Trong Sales, giả sử một aggregate "Order" gồm phần đầu đơn và các dòng hàng. Những quy tắc phải được thực thi nhất quán có thể là:

- Mỗi dòng có số lượng dương; đơn phải có ít nhất một dòng trước khi được xác nhận.
- Đơn giá và loại tiền tại lúc chốt đơn phải được giữ nguyên sau xác nhận.
- Chuyển trạng thái tuân theo quy trình được phép: "PENDING" sang "CONFIRMED" hoặc "CANCELLED"; đơn đã hủy không thể trở lại chờ xử lý bằng một lệnh cập nhật tùy ý.
- Nếu lưu tổng tiền trong phần đầu đơn, tổng đó phải khớp với tổng các dòng và quy tắc làm tròn đã thống nhất.

Các quy tắc này thuộc trách nhiệm của Sales và có thể kiểm tra trong một giao dịch cập nhật Order. Ngược lại, câu "đơn chỉ được xác nhận sau khi kho giữ đủ hàng và thanh toán thành công" cần **kết quả từ nhiều ngữ cảnh**. Không nên mặc định một transaction SQL trải dài qua Sales, Inventory và Payment, đặc biệt khi chúng là những hệ thống độc lập.

Một cách phối hợp là quy trình (*saga/process manager*) với trạng thái trung gian rõ ràng:

1. Sales tạo đơn "PENDING" cùng giá và dòng hàng đã chốt.
2. Sales gửi lệnh giữ hàng kèm mã đơn; Inventory xử lý nguyên tử quy tắc tồn kho của mình và trả "RESERVED" hoặc "REJECTED".
3. Nếu giữ hàng thành công, Sales yêu cầu Payment ủy quyền/thực hiện thanh toán. Nếu thất bại, Sales yêu cầu Inventory giải phóng phần giữ và chuyển đơn sang trạng thái phù hợp.
4. Khi các điều kiện cần đều đạt, Sales chuyển đơn sang "CONFIRMED".

Trong khoảng thời gian chờ, toàn hệ thống có thể **nhất quán cuối cùng** (*eventual consistency*): Inventory đã giữ hàng nhưng Sales chưa nhận sự kiện xác nhận. Điều này chấp nhận được nếu trạng thái trung gian hiển thị đúng và có cơ chế phục hồi.

Để luồng hoạt động an toàn khi thông điệp bị gửi lại, mất phản hồi hoặc đến trễ:

- Dùng mã yêu cầu/đặt giữ duy nhất để xử lý **idempotent** (nhận lại cùng lệnh không giữ hàng hai lần).
- Lưu trạng thái và phiên bản để kiểm soát cập nhật đồng thời.
- Cân nhắc **transactional outbox** khi cần ghi dữ liệu và thông điệp sự kiện một cách đáng tin cậy trong cùng giao dịch cục bộ; phía nhận theo dõi sự kiện đã xử lý.
- Xác định thời hạn giữ hàng, cơ chế thử lại và thao tác bù (*compensation*) khi bước sau thất bại. Thao tác bù là nghiệp vụ mới, không phải nút "rollback" xuyên dịch vụ.

Các lựa chọn đồng bộ hay bất đồng bộ tùy mức độ chấp nhận độ trễ và thất bại của nghiệp vụ. "Eventual consistency" không có nghĩa bỏ kiểm soát ràng buộc; nó đòi hỏi định nghĩa rõ trạng thái tạm, điểm kết thúc và quy trình xử lý lỗi.

## 5. Từ ranh giới miền sang lược đồ quan hệ

Ví dụ dưới đây minh họa trên **PostgreSQL**. Catalog và Sales dùng hai schema trong cùng database để phân định quyền sở hữu logic. Đây là một lựa chọn triển khai cho hệ thống nguyên khối có module; có thể tách database khi nhu cầu độc lập vận hành xuất hiện.

~~~sql
CREATE SCHEMA catalog;
CREATE SCHEMA sales;

CREATE TABLE catalog.product (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    current_list_price NUMERIC(14, 2) NOT NULL
        CHECK (current_list_price >= 0),
    currency CHAR(3) NOT NULL
);

CREATE TABLE sales.orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    buyer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sales.order_line (
    order_id BIGINT NOT NULL REFERENCES sales.orders(id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    catalog_product_id BIGINT NOT NULL,
    product_name_snapshot TEXT NOT NULL,
    unit_price_snapshot NUMERIC(14, 2) NOT NULL
        CHECK (unit_price_snapshot >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    currency CHAR(3) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
~~~

Những quyết định có chủ ý:

- "sales.order_line" có khóa ngoại về "sales.orders" vì chúng cùng một mô hình và có vòng đời gắn chặt.
- "catalog_product_id" là tham chiếu đến Catalog, **không có khóa ngoại xuyên schema** trong ví dụ. Sales xác minh sản phẩm qua hợp đồng nghiệp vụ khi lập đơn và lưu mã để đối soát.
- "product_name_snapshot" và "unit_price_snapshot" là dữ liệu lịch sử có chủ đích. Cập nhật tên hoặc giá hiện hành không được sửa đơn đã chốt.
- Khóa chính ghép "(order_id, line_no)" đảm bảo số thứ tự dòng duy nhất trong một đơn và hỗ trợ truy vấn các dòng theo "order_id". Chỉ thêm chỉ mục mới sau khi có nhu cầu truy vấn thực tế.
- Ràng buộc "CHECK" bảo vệ các điều kiện theo từng hàng. Các quy tắc nhiều hàng như "đơn xác nhận phải có ít nhất một dòng" hoặc quy tắc chuyển trạng thái cần xử lý trong giao dịch ở tầng miền/ứng dụng, hoặc bằng cơ chế cơ sở dữ liệu phù hợp nếu được thiết kế kỹ. Riêng "CHECK(status IN (...))" **không** kiểm tra chuyển trạng thái hợp lệ.

Ví dụ chống hai người cùng xác nhận/sửa một phiên bản đơn:

~~~sql
UPDATE sales.orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE id = :order_id
  AND status = 'PENDING'
  AND version = :expected_version;
~~~

Ứng dụng phải kiểm tra số hàng được cập nhật. Nếu bằng 0, dữ liệu hoặc trạng thái đã thay đổi; cần đọc lại và quyết định xử lý nghiệp vụ thay vì ghi đè. Trước câu lệnh này, ứng dụng còn phải xác minh đã nhận đủ kết quả giữ hàng và thanh toán tương ứng với đơn. **Optimistic locking** chỉ xử lý cạnh tranh ghi, không tự thực hiện toàn bộ quy tắc xác nhận.

Nếu hệ thống đa tiền tệ, không được cộng trực tiếp các giá trị khác "currency"; quy định rõ loại tiền đơn, tỷ giá tại thời điểm tính và chính sách làm tròn. Ví dụ trên được rút gọn nhằm tập trung vào ranh giới mô hình.

## 6. Thiết kế hợp đồng giữa các ngữ cảnh

Khi Sales nhận thông tin từ Catalog hoặc Inventory, hãy mô tả hợp đồng ở mức nghiệp vụ:

| Hợp đồng | Dữ liệu tối thiểu | Điều người nhận cần biết |
| --- | --- | --- |
| ProductPublished / ProductChanged | productId, version, name, listPrice, currency | Dữ liệu mô tả **giá hiện hành**, không thay thế giá của đơn cũ |
| ReserveStock (lệnh) | requestId, orderId, sku, quantity | Cùng requestId phải có kết quả xử lý ổn định khi gửi lại |
| StockReserved / StockRejected | eventId, requestId, reservationId, outcome | Sales liên kết kết quả với yêu cầu đã phát ra |
| PaymentAuthorized / PaymentFailed | eventId, orderId, paymentId, outcome | Chỉ tin kết quả từ nguồn Payment; xử lý trùng/lỗi thứ tự |

Tên sự kiện ở đây là ví dụ, không phải chuẩn bắt buộc. Đặc biệt, **lệnh** yêu cầu làm gì đó khác với **sự kiện** thông báo việc đã xảy ra. Khi thiết kế thông điệp, nêu rõ người sở hữu hợp đồng, phiên bản schema, ý nghĩa thời gian và chính sách tương thích với phiên bản cũ.

Nếu Sales dùng từ "đã thanh toán" nhưng Payment phân biệt "AUTHORIZED" (đã ủy quyền) và "CAPTURED" (đã thu tiền), cần một lớp chuyển đổi/biên dịch (*anti-corruption layer*) để tránh gán sai ý nghĩa. Việc ghép hai bảng bằng cột trạng thái trùng tên không giải quyết được sai lệch ngữ nghĩa.

**Context map** ghi lại các ngữ cảnh, quan hệ phụ thuộc và cách tích hợp. Nó hữu ích hơn sơ đồ bảng toàn hệ thống khi cần xác định nơi đổi quy tắc, nơi tiêu thụ dữ liệu và nơi phải phối hợp thay đổi hợp đồng.

## 7. Nhất quán cho truy vấn và báo cáo

Một màn hình "chi tiết đơn hàng" thường ghép dữ liệu từ Sales, Inventory và Payment. Có hai chiến lược thường gặp:

- **Ghép khi đọc:** gọi API của các ngữ cảnh; dữ liệu có thể mới nhưng độ trễ và tính sẵn sàng phụ thuộc các lời gọi.
- **Mô hình đọc riêng:** nhận sự kiện để xây projection dành cho tra cứu, dashboard hoặc báo cáo. Mô hình đọc có thể trễ và cần ghi rõ "cập nhật lần cuối".

Không biến mô hình báo cáo thành "nguồn sự thật" cho việc sửa đơn, điều chỉnh tồn kho hay thanh toán. Nếu số lượng hiển thị tạm thời lệch với nguồn gốc, cần xác định giới hạn độ trễ cho phép, thời điểm làm mới, cách đối soát và hành vi giao diện. Với truy vấn tài chính quan trọng, có thể yêu cầu đối chiếu nguồn có thẩm quyền trước khi quyết định.

## 8. Ranh giới miền không phụ thuộc công nghệ lưu trữ

Một bounded context không nhất thiết tương ứng với một bảng, một schema, một kiểu database hay một microservice. Khi chọn mô hình vật lý, hãy bắt đầu từ các bất biến, dạng truy vấn và khả năng mở rộng:

| Cách lưu trữ | Khi có lợi | Điều cần lưu ý về ranh giới nhất quán |
| --- | --- | --- |
| **Quan hệ** | Giao dịch nhiều hàng, khóa, ràng buộc và truy vấn có cấu trúc | Dùng transaction và constraint cho bất biến cục bộ; hạn chế tạo phụ thuộc tùy tiện qua ngữ cảnh |
| **Document** | Dữ liệu được đọc/ghi theo cụm, cấu trúc lồng nhau thay đổi linh hoạt | Một document có thể là đơn vị cập nhật nguyên tử tùy hệ quản trị; không nhúng vô hạn những thực thể có vòng đời riêng |
| **Đồ thị** | Quan hệ nhiều bước, mạng liên kết cần duyệt linh hoạt | Cạnh nối nhiều thực thể không tự chỉ ra ai sở hữu dữ liệu hoặc giao dịch nào phải nguyên tử |
| **Phân tích/cột** | Báo cáo và tổng hợp khối lượng lớn | Thường là bản sao phục vụ đọc; có độ trễ ingest và không thay thế nguồn giao dịch |

Ví dụ Sales có thể dùng bảng "orders"/"order_line" hoặc document Order chứa danh sách dòng. Điều quyết định vẫn là: Sales sở hữu giá đã chốt, những bất biến nào cần bảo vệ, và những thay đổi nào đến từ ngữ cảnh khác.

## 9. Quy trình xác định ranh giới khi nhận yêu cầu

**Bước 1 – Thu thập tình huống nghiệp vụ.** Hỏi người thực hiện công việc: Ai tạo đơn? Khi nào giá được chốt? Ai có quyền hủy đặt giữ? "Đã thanh toán" có nghĩa đã ủy quyền hay đã thực thu?

**Bước 2 – Lập bảng thuật ngữ theo vai trò.** Ghi cùng một từ ở từng phòng ban cùng định nghĩa và ví dụ. Những chỗ từ giống nhau nhưng quy tắc khác nhau là dấu hiệu cần phân định ngữ cảnh.

**Bước 3 – Xác định nguồn dữ liệu có thẩm quyền.** Với từng thông tin, ghi ai được tạo/sửa/xóa, ai chỉ được đọc hay lưu bản chụp. Tránh hai ngữ cảnh cùng là chủ sở hữu một giá trị mà không có cơ chế phân xử.

**Bước 4 – Viết bất biến và yêu cầu thời gian.** Đánh dấu điều kiện phải đúng ngay khi commit, điều kiện có thể chờ thông điệp, và độ trễ tối đa nghiệp vụ chấp nhận. Xếp các thực thể cần thay đổi nguyên tử thành aggregate phù hợp.

**Bước 5 – Thiết kế tích hợp.** Chỉ ra API, lệnh, sự kiện, mã định danh, chính sách retry/idempotency, phiên bản và cơ chế bù. Với báo cáo, xác định dữ liệu gốc và bản sao đọc.

**Bước 6 – Chuyển thành lược đồ và kiểm chứng.** Tạo khóa, kiểu, constraint, chỉ mục phục vụ truy vấn, quyền truy cập và migration; thử các tình huống cạnh tranh, trùng sự kiện và thay đổi quy tắc.

Kết quả nên gồm tối thiểu: sơ đồ ngữ cảnh, bảng trách nhiệm dữ liệu, danh sách bất biến, sơ đồ aggregate chính, hợp đồng tích hợp và các kịch bản chấp nhận. Chỉ vẽ ERD tổng thể mà bỏ qua những câu hỏi này sẽ che mất nơi mô hình bắt đầu và kết thúc.

## 10. Các dấu hiệu phân chia sai

| Dấu hiệu | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Một bảng "product" dùng cho cả danh mục, đơn cũ và kho | Sửa giá/thuộc tính có thể làm sai lịch sử; tranh chấp quyền ghi | Chỉ định chủ sở hữu, dùng snapshot và bản dịch dữ liệu theo mục đích |
| Cứ một bảng hoặc một service là một bounded context | Mô hình bị chia vụn, tích hợp nhiều, giao dịch nghiệp vụ khó thực hiện | Chia theo ngôn ngữ và quy tắc, rồi mới thiết kế triển khai |
| Mọi ràng buộc đều phải ACID trên nhiều ngữ cảnh | Khóa chéo, phụ thuộc hạ tầng, khó chịu lỗi | Giữ bất biến cục bộ trong aggregate; thiết kế workflow có trạng thái và bù |
| Chia sẻ ORM entity hoặc schema giữa các nhóm | Thay đổi cấu trúc bên này âm thầm phá mô hình bên kia | Dùng hợp đồng được quản lý phiên bản và ánh xạ tại biên |
| Sao chép dữ liệu mà không biết ai sở hữu | Hai nơi đều cho phép sửa, dễ phân kỳ không thể hòa giải | Chỉ một nguồn có quyền quyết định; bản sao ghi rõ mục đích và độ trễ |
| Chỉ kiểm tra "status" bằng CHECK | Vẫn chuyển được từ CANCELLED thẳng sang CONFIRMED | Đưa luật chuyển trạng thái vào thao tác miền có kiểm soát đồng thời |

## 11. Bài tập thực hành có lời giải định hướng

**Tình huống:** Một nền tảng đặt vé xem phim có ba nghiệp vụ: (A) công bố lịch chiếu và giá niêm yết; (B) giữ ghế trong 5 phút để chống bán trùng; (C) lập đơn và thu tiền. Sau khi khách mua vé, nhà rạp có thể đổi giá niêm yết, nhưng tiền của vé đã mua phải giữ nguyên. Một lệnh thanh toán có thể bị gửi lại do mất kết nối.

**Yêu cầu:**

1. Đề xuất các bounded context và dữ liệu do mỗi ngữ cảnh sở hữu.
2. Viết hai bất biến cần bảo đảm ngay trong giao dịch cục bộ và một quy tắc phải phối hợp qua nhiều ngữ cảnh.
3. Giải thích cách lưu giá vé đã mua, cách tránh bán trùng ghế và cách xử lý lệnh thanh toán lặp.

**Một hướng giải hợp lệ:**

- **Showtime/Catalog** sở hữu suất chiếu, thông tin phim và giá hiện hành. **Seat Inventory** sở hữu ghế còn trống, giữ ghế và thời hạn giữ. **Booking** sở hữu đặt vé và giá chốt. **Payment** sở hữu giao dịch trả tiền và mã idempotency.
- Bất biến cục bộ của Seat Inventory: một ghế của một suất chiếu tại một thời điểm không thể có hai quyền giữ/đặt còn hiệu lực; thao tác giữ ghế phải xử lý cạnh tranh nguyên tử. Bất biến cục bộ của Booking: tổng tiền và đơn giá của vé đã chốt không tự thay đổi khi Catalog cập nhật giá. Quy tắc xuyên ngữ cảnh: chỉ phát hành vé hợp lệ sau khi có quyền giữ/đặt ghế thành công và trạng thái thanh toán đáp ứng yêu cầu.
- Booking lưu "price_snapshot" kèm loại tiền. Seat Inventory dùng khóa/ràng buộc và thao tác có điều kiện phù hợp với cách biểu diễn ghế và thời hạn; cần xử lý hạn giữ bằng quy trình giải phóng rõ ràng. Payment lưu khóa idempotency để cùng một lệnh không thu tiền hai lần; Booking xử lý các kết quả trùng bằng mã sự kiện và trạng thái đã biết.

Hãy kiểm tra thêm các tình huống: hai khách cùng giữ ghế, giữ hết hạn trước khi tiền về, khách bấm "Thanh toán" hai lần, và thay đổi giá giữa lúc xem lịch chiếu và lúc xác nhận. Mỗi tình huống phải nêu rõ ngữ cảnh quyết định, dữ liệu bị thay đổi, phạm vi giao dịch và cách phục hồi.

## 12. Checklist rà soát mô hình

- Có thể giải thích ý nghĩa của mỗi thuật ngữ quan trọng **trong đúng ngữ cảnh** không?
- Mỗi dữ liệu có một bên sở hữu, và bản sao có mục đích, tuổi dữ liệu, quy tắc cập nhật rõ ràng không?
- Mỗi bất biến quan trọng thuộc aggregate/giao dịch cục bộ nào? Có quy tắc nào đang âm thầm đòi transaction qua nhiều hệ thống không?
- Mối quan hệ nào là khóa ngoại nội bộ, mối quan hệ nào là tham chiếu qua hợp đồng?
- Có kiểm soát cập nhật đồng thời, lệnh lặp, sự kiện đến trễ, lỗi giữa chừng và bước bù không?
- Lược đồ, loại storage, chỉ mục và cách triển khai có phục vụ đúng nghiệp vụ thay vì áp đặt ngược cách chia mô hình không?

**Kết luận:** Ngữ cảnh giới hạn xác định **nơi một mô hình và ngôn ngữ có hiệu lực**. Aggregate xác định **những thay đổi nào cần nhất quán ngay trong một giao dịch**. Database, schema và service là **các lựa chọn triển khai**. Phân biệt rõ ba lớp này giúp chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu chính xác, có thể tiến hóa và được kiểm chứng bằng các kịch bản thực tế.
