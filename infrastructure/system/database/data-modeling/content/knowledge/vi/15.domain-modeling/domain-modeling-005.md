# Tham chiếu bằng định danh giữa các aggregate

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao quan hệ **giữa hai aggregate** thường được biểu diễn bằng **định danh của aggregate root** thay vì nhúng và điều khiển trực tiếp toàn bộ đối tượng bên kia.
- Phân biệt tham chiếu ID, khóa ngoại trong cơ sở dữ liệu, bản chụp dữ liệu (*snapshot*) và dữ liệu sao chép phục vụ đọc.
- Thiết kế định danh có phạm vi, tính ổn định và ngữ nghĩa rõ ràng; áp dụng kiểu ID riêng để tránh ghép sai các đối tượng.
- Quyết định lúc nào kiểm tra sự tồn tại, trạng thái hoặc quyền truy cập của một tham chiếu và xử lý trường hợp nguồn dữ liệu thay đổi, bị xóa hoặc chưa đồng bộ.
- Ánh xạ quan hệ xuyên aggregate sang lược đồ quan hệ, document, đồ thị và mô hình phân tích mà vẫn bảo vệ các bất biến và đường ghi.
- Nhận diện rủi ro về transaction, đồng thời, toàn vẹn dữ liệu và phân quyền khi chuyển từ sơ đồ nghiệp vụ sang thiết kế vật lý.

Trong module **DATABASE_DATA_MODELING**, nhiều mối quan hệ trong yêu cầu nghiệp vụ không đồng nghĩa với việc tất cả thực thể phải được nạp và ghi cùng nhau. Chẳng hạn đơn hàng thuộc một khách, gồm các mặt hàng từ danh mục và có kết quả giữ hàng từ kho. Hệ thống cần **liên kết** các thông tin đó nhưng mỗi nhóm dữ liệu có người sở hữu và vòng đời riêng. Dùng định danh để tham chiếu là một cách diễn đạt ranh giới này ngay trong mô hình.

## 1. Định danh là liên kết, không phải quyền sở hữu

**Aggregate** là nhóm đối tượng có một **aggregate root** chịu trách nhiệm bảo vệ những bất biến cần nhất quán trong một giao dịch cục bộ. **Tham chiếu bằng định danh** nghĩa là một aggregate giữ giá trị nhận diện của root khác, chẳng hạn Order giữ customerId thay vì chứa một đối tượng Customer đầy đủ có thể sửa.

Giả sử một hệ thống bán hàng có bốn aggregate:

| Aggregate | Chủ sở hữu dữ liệu và bất biến chính | Định danh của root |
| --- | --- | --- |
| Customer | Hồ sơ, trạng thái tài khoản, thông tin liên hệ hiện hành | customerId |
| Product | Mã hàng, tên và thông tin chào bán hiện hành | productId |
| Order | Dòng hàng, giá đã chốt, thông tin giao dịch và trạng thái đơn | orderId |
| StockReservation | Quyền giữ số lượng hàng trong kho, thời hạn và kết quả giữ | reservationId |

Quan hệ có thể được diễn đạt:

~~~mermaid
flowchart TB
    U["Use case: Đặt hàng"]
    U --> O

    subgraph SALES["Sales — Aggregate Order"]
        O["Order root<br/>orderId, customerId"]
        L["OrderLine<br/>productId, priceSnapshot"]
        O -->|"quản lý dòng hàng"| L
    end

    C["Customer root"]
    P["Product root"]
    R["StockReservation root"]
    O -.->|"customerId"| C
    L -.->|"productId"| P
    O -.->|"reservationId (khi có)"| R
~~~

Đường liền biểu diễn thành viên do Order điều phối. Đường đứt biểu diễn **liên hệ qua định danh**. Dữ liệu Customer có thể đổi email; Catalog có thể đổi giá; kho có thể hết hạn giữ hàng, nhưng Order vẫn có danh tính và quy tắc cập nhật riêng.

Tham chiếu ID **không có nghĩa** root bên kia đã được nạp vào bộ nhớ, luôn tồn tại tại thời điểm đọc hay được phép thay đổi bởi mã đang giữ ID. Mọi thao tác ảnh hưởng aggregate được tham chiếu phải đi qua chủ sở hữu có thẩm quyền của nó.

### Ba khái niệm cần phân biệt

| Khái niệm | Nằm ở đâu? | Bảo đảm điều gì? | Không tự bảo đảm điều gì? |
| --- | --- | --- | --- |
| **Tham chiếu miền bằng ID** | Thuộc tính hoặc value object trong mô hình | Diễn đạt đối tượng khác mà nghiệp vụ đang nói tới | Sự tồn tại, trạng thái mới nhất hay quyền truy cập |
| **Khóa ngoại (foreign key)** | Lược đồ của cơ sở dữ liệu quan hệ | Theo cấu hình, bảo đảm giá trị khóa trỏ tới hàng tồn tại trong cùng cơ sở dữ liệu | Bản ghi thuộc đúng ngữ cảnh, người ghi có quyền, trạng thái nghiệp vụ hợp lệ |
| **Snapshot** | Dữ liệu lịch sử được lưu bởi bên tiêu thụ | Bảo tồn giá trị tại một thời điểm được xác định | Tự đồng bộ với dữ liệu hiện hành bên nguồn |

Đây là ba công cụ có thể **được dùng cùng nhau** tùy yêu cầu. DDD thường khuyến khích liên kết qua root ID để giảm phụ thuộc trong mô hình; không có quy tắc rằng mọi tham chiếu ID đều phải cấm khóa ngoại trong mọi hệ thống.

## 2. Vì sao không tham chiếu trực tiếp bằng đối tượng?

Hãy tưởng tượng lớp Order chứa một trường Customer kiểu đối tượng, và Customer lại chứa danh sách Order; Product chứa các OrderLine đã mua. Nếu mọi thao tác đều có thể đi xuyên qua các trường và sửa dữ liệu, những vấn đề xuất hiện:

1. **Không rõ quyền ghi:** thay địa chỉ giao hàng trong Order có thể vô tình sửa hồ sơ Customer đang dùng cho các đơn khác.
2. **Vòng đời bị ghép:** thao tác xóa Product có thể bị hiểu là phải xóa cả dòng Order lịch sử.
3. **Tải dữ liệu quá rộng:** nạp một Order có thể kéo theo Customer, toàn bộ Order của Customer và cây Product liên quan.
4. **Transaction mơ hồ:** lập trình viên có thể giả định sửa một object graph là một giao dịch nguyên tử dù dữ liệu nằm ở nhiều aggregate hoặc service.
5. **Khó tiến hóa:** thay đổi cấu trúc Product buộc mã Sales biết chi tiết mới dù Sales chỉ cần productId và giá đã chốt.

Thay bằng **customerId**, **productId** và hợp đồng truy cập giúp nói rõ: Order biết **đối tượng nào**, nhưng không mặc nhiên sở hữu **trạng thái nội bộ** của đối tượng ấy.

> Quy tắc thiết kế hữu ích: **bên ngoài một aggregate thao tác qua root của aggregate đó; quan hệ với aggregate khác chủ yếu được diễn đạt bằng ID của root**. Trong một số cách triển khai, có thể nạp object liên quan để đọc, nhưng không để tham chiếu ấy trở thành đường ghi bỏ qua quyền sở hữu.

## 3. Chọn định danh có ngữ nghĩa và phạm vi đúng

Một ID tốt cần giải quyết ba câu hỏi: nó nhận diện **loại đối tượng gì**, duy nhất **trong phạm vi nào**, và có **ổn định theo vòng đời** không?

### 3.1. ID nghiệp vụ và khóa lưu trữ

Ví dụ Product có ID nội bộ dạng UUID và mã SKU như LAPTOP-14. SKU có thể thay khi doanh nghiệp tái phân loại, tái sử dụng hoặc hợp nhất danh mục; UUID có thể ổn định hơn để làm khóa liên kết. Ngược lại, trong một số miền, chính SKU là danh tính được quản lý nghiêm ngặt. Không có công thức chọn UUID cho mọi bài toán: trước hết phải hỏi nghiệp vụ liệu mã có thể thay, có thể trùng theo kho/nhà bán hay không.

| Loại định danh | Ví dụ | Rủi ro cần xét |
| --- | --- | --- |
| Khóa sinh nội bộ | UUID, BIGINT identity | Khi đưa ra ngoài hệ thống cần chính sách lộ diện, ánh xạ và tính ổn định |
| Mã nghiệp vụ | orderNumber, contractCode | Có thể đổi định dạng, phạm vi duy nhất hoặc quy tắc sinh theo năm/chi nhánh |
| Khóa ghép có phạm vi | (tenantId, productId), (offeringId, seatNo) | Bỏ phần phạm vi có thể trỏ sang đối tượng khác |
| ID từ hệ thống đối tác | externalCustomerId, paymentProviderId | Chỉ duy nhất trong nhà cung cấp/namespace tương ứng; cần phân biệt ID nội bộ |

**Không dùng email, số điện thoại hay tên người làm ID mặc định:** các giá trị ấy có thể đổi và còn chứa dữ liệu cá nhân không cần đưa vào mọi bản ghi tích hợp.

### 3.2. Phạm vi tenant và namespace

Trong hệ thống nhiều tổ chức (*multi-tenant*), mã sản phẩm 42 của tenant A có thể khác mã 42 của tenant B. Khi đó định danh đầy đủ là (tenantId, productId), trừ khi sản phẩm được cấp ID duy nhất toàn hệ thống bằng quy tắc được bảo đảm.

Một câu truy vấn chỉ có điều kiện product_id = 42 có thể trả về sai tổ chức; vì vậy phạm vi tenant phải được mang xuyên qua lược đồ, API, truy vấn và chính sách phân quyền.

**ID không phải giấy phép truy cập.** Biết một UUID không cho phép người dùng đọc hoặc sửa aggregate đó. Application service vẫn phải kiểm quyền trên đối tượng và tenant; lớp truy cập database có thể bổ sung Row-Level Security hoặc cơ chế tương đương.

### 3.3. Kiểu ID riêng trong mã nguồn

Nếu customerId và productId đều là UUID trần, việc truyền nhầm hai tham số có thể không bị trình biên dịch phát hiện. Có thể bọc ID bằng value object:

~~~java
import java.util.Objects;
import java.util.UUID;

record CustomerId(UUID value) {
    CustomerId {
        Objects.requireNonNull(value);
    }
}

record ProductId(UUID value) {
    ProductId {
        Objects.requireNonNull(value);
    }
}

record OrderId(UUID value) {
    OrderId {
        Objects.requireNonNull(value);
    }
}

record ProductReference(ProductId productId, String nameSnapshot) {
    ProductReference {
        Objects.requireNonNull(productId);
        Objects.requireNonNull(nameSnapshot);
    }
}

final class Order {
    private final OrderId id;
    private final CustomerId customerId;

    Order(OrderId id, CustomerId customerId) {
        this.id = Objects.requireNonNull(id);
        this.customerId = Objects.requireNonNull(customerId);
    }

    OrderId id() { return id; }
    CustomerId customerId() { return customerId; }
}
~~~

Ở đây **CustomerId** là value object nhận diện một **Customer entity** khác. Không có mâu thuẫn: giá trị ID không có vòng đời nghiệp vụ riêng, còn đối tượng mà nó nhận diện vẫn là entity có danh tính. Khi ánh xạ sang SQL, các ID wrappers có thể được chuyển thành UUID; lưu và phục hồi phải giữ đúng loại ID.

## 4. ID, snapshot hay nhúng đối tượng: quyết định theo nhu cầu

Hãy phân tích một yêu cầu đơn hàng:

| Nhu cầu | Cách biểu diễn phù hợp | Lý do |
| --- | --- | --- |
| Biết đơn thuộc khách nào để truy vấn chủ sở hữu | customerId | Liên kết tới Customer với vòng đời riêng |
| Lưu tên và địa chỉ nhận hàng lúc xác nhận | recipientNameSnapshot, shippingAddressSnapshot | Bảo toàn giao dịch dù hồ sơ khách đổi |
| Ghi mặt hàng nào đã được mua | productId | Đối chiếu danh mục hoặc truy nguồn nghiệp vụ |
| Bảo toàn tên hàng, giá mua, tiền tệ tại lúc chốt | productNameSnapshot, priceSnapshot | Giá và tên Catalog hôm nay có thể khác hôm mua |
| Đổi số lượng một dòng trong Order DRAFT | OrderLine do Order quản lý | Bất biến trạng thái và tổng tiền thuộc Order |
| Hiển thị tên khách đang dùng trên màn hình quản trị | Truy vấn Customer hoặc read model | Cần dữ liệu mới nhất hoặc độ trễ được chấp nhận |
| Lưu kết quả giữ hàng còn hiệu lực | reservationId, trạng thái kết quả đã nhận, thời hạn | Không tự sửa StockReservation từ Order |

**Snapshot và ID bổ sung cho nhau.** Chỉ dùng snapshot sẽ mất khả năng đối chiếu đối tượng gốc; chỉ dùng ID và đọc dữ liệu mới nhất sẽ làm dữ liệu lịch sử đổi nghĩa. Khi một đối tượng có vòng đời phụ thuộc trực tiếp root và phải được sửa cùng root, mới cân nhắc đưa nó vào **cùng aggregate**.

Đối với dữ liệu đọc thuần, không cần tạo một aggregate khổng lồ. Có thể dùng truy vấn kết hợp hoặc projection riêng; mô hình đọc phục vụ câu hỏi khác với mô hình ghi.

## 5. Điều gì được bảo đảm khi liên kết qua ID?

Một tham chiếu không tự tạo tính nhất quán. Cần phân biệt ba mức kiểm tra:

1. **Đúng cấu trúc:** ID đúng kiểu và có phạm vi hợp lệ. Ví dụ productId là UUID và tenantId có giá trị.
2. **Có thật:** đối tượng được tham chiếu tồn tại theo dữ liệu có thẩm quyền tại thời điểm cần kiểm tra.
3. **Được phép sử dụng:** đối tượng đang ở trạng thái nghiệp vụ phù hợp. Product có thể tồn tại nhưng ngừng bán; Customer có thể tồn tại nhưng bị khóa.

Các mức này có thể cần kiểm tra tại các thời điểm khác nhau. Ví dụ:

- Khi **tạo Order DRAFT**, Sales có thể cần xác nhận Customer thuộc tenant và Product đang được phép đặt.
- Khi **xác nhận Order**, Sales phải kiểm tra những điều kiện quan trọng đúng ở thời điểm xác nhận, ví dụ giá được chấp nhận theo phiên bản báo giá còn hiệu lực và kết quả giữ hàng chưa hết hạn.
- Khi **đọc Order lịch sử**, Sales không nhất thiết phải yêu cầu Product còn đang bán. Thông tin đã mua được bảo tồn bằng snapshot.

Nếu một Customer bị xóa sau khi Order đã xác nhận, điều đó không có nghĩa Order lập tức trở nên vô hiệu. Cần chính sách vòng đời và lưu trữ lịch sử: giữ định danh phục vụ đối soát khi hợp lệ, ẩn danh dữ liệu cá nhân theo quy định, hoặc ghi tombstone cho đối tượng đã ngừng hoạt động.

### Cửa sổ thời gian giữa kiểm tra và ghi

Xét quy trình:

~~~text
T1: Sales hỏi Catalog: Product P đang bán? -> Có
T2: Catalog đổi P sang DISCONTINUED
T3: Sales ghi Order tham chiếu P
~~~

Kiểm tra ở T1 không bảo đảm trạng thái Product vẫn vậy ở T3. Đây là vấn đề **time-of-check to time-of-use (TOCTOU)**. Cách xử lý phải phù hợp quy tắc nghiệp vụ:

- Nếu đơn được phép dựa trên **báo giá còn hiệu lực**, hãy nhận một quoteId/version cùng thời hạn cam kết rồi xác nhận theo hợp đồng đó.
- Nếu Product bắt buộc đang bán **đúng lúc xác nhận**, cần đặt bước xác nhận tại chủ sở hữu Product hoặc giao thức có điểm tuyến tính hóa rõ ràng; một request kiểm tra thông thường có thể bị thay đổi ngay sau khi trả kết quả.
- Nếu chỉ cần "đã được công bố lúc tạo DRAFT", snapshot kèm timestamp và nguồn xác thực có thể đủ.

Việc tham chiếu bằng ID buộc ta mô tả **cam kết nào thật sự cần**; nó không tự giải quyết race bằng cách đặt hai ID cạnh nhau.

## 6. Ánh xạ sang SQL: khóa ngoại nội bộ, ID xuyên aggregate

Trong ví dụ PostgreSQL sau, Sales sở hữu Order và OrderLine. Customer và Catalog là những mô hình khác, có thể nằm cùng hoặc khác database; Sales lưu ID của chúng nhưng không quản lý vòng đời của chúng.

~~~sql
CREATE SCHEMA IF NOT EXISTS sales;

CREATE TABLE sales.orders (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    recipient_name_snapshot TEXT NOT NULL,
    shipping_address_snapshot JSONB NOT NULL
        CHECK (jsonb_typeof(shipping_address_snapshot) = 'object'),
    status VARCHAR(16) NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, order_id)
);

CREATE TABLE sales.order_line (
    tenant_id UUID NOT NULL,
    order_id UUID NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id UUID NOT NULL,
    sku_snapshot TEXT NOT NULL,
    product_name_snapshot TEXT NOT NULL,
    unit_price_amount NUMERIC(19, 2) NOT NULL
        CHECK (unit_price_amount >= 0),
    currency_code CHAR(3) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales.orders(tenant_id, order_id)
);

-- Truy vấn đơn của một khách trong một tenant theo thời gian.
CREATE INDEX orders_by_customer
    ON sales.orders(tenant_id, customer_id, created_at DESC);
~~~

Các quyết định có ý nghĩa miền:

- **Khóa chính (tenant_id, order_id)** xác định Order trong phạm vi tenant. OrderLine tham chiếu Order qua **FK ghép** để không vô tình liên kết dòng thuộc tenant khác.
- **customer_id** và **product_id** là ID tham chiếu sang root khác. Mã Sales biết đối tượng nào liên quan, nhưng không tự cấp quyền sửa Customer hay Catalog.
- **recipient_name_snapshot**, **shipping_address_snapshot**, **product_name_snapshot** và **unit_price_amount** là thông tin lưu tại thời điểm nghiệp vụ xác định. Lớp ứng dụng cần thống nhất lúc nào snapshot được chốt.
- **CHECK** bảo vệ tính hợp lệ của từng hàng; nó không kiểm tra Product đang được phép bán hay Customer được quyền mua. Ràng buộc liên nguồn thuộc hợp đồng nghiệp vụ.
- Chỉ mục orders_by_customer phục vụ truy vấn thực tế giả định; các chỉ mục khác nên xuất phát từ workload và kế hoạch truy vấn, tránh tạo tất cả chỉ mục có thể nghĩ ra.

### Có nên dùng khóa ngoại từ Sales sang Catalog hoặc Customer?

Không có đáp án cấm hoặc bắt buộc tuyệt đối:

| Điều kiện triển khai | FK xuyên aggregate có thể hữu ích khi | Cần cân nhắc khi |
| --- | --- | --- |
| Cùng database và cùng chủ sở hữu vòng đời | Muốn DB chặn tham chiếu đến hàng không tồn tại, kiểm soát thao tác xóa thống nhất | FK không bảo vệ trạng thái nghiệp vụ; dùng ON DELETE CASCADE có thể phá lịch sử |
| Cùng database nhưng bounded context độc lập | Có thể chủ động chấp nhận liên kết trong monolith ổn định | Migration, quyền truy cập và thời điểm xóa bị ràng buộc xuyên ngữ cảnh |
| Khác database/service | Không có FK SQL trực tiếp qua database độc lập | Cần API/event, kiểm tra khi command, chính sách dữ liệu mất liên kết và đối soát |

Trong mẫu trên không có FK trực tiếp đến Customer/Product vì chủ sở hữu có thể triển khai độc lập. Đó là **lựa chọn kiến trúc**; bỏ FK không có nghĩa cho phép dữ liệu tham chiếu rác. Cần xác định cơ chế kiểm tra, sự kiện vòng đời và khả năng sửa chữa dữ liệu mất liên kết.

### Transaction và optimistic locking vẫn cần ở aggregate sở hữu

OrderLine thuộc Order, nên mọi thao tác sửa dòng phải tuân thủ trạng thái và phiên bản của Order:

~~~sql
BEGIN;

UPDATE sales.orders
SET version = version + 1
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND status = 'DRAFT'
  AND version = :expected_version;

-- Bắt buộc kiểm tra đúng một hàng được cập nhật.
-- Nếu bằng 0 thì ROLLBACK và xử lý xung đột/quyền truy cập.

UPDATE sales.order_line
SET quantity = :new_quantity
WHERE tenant_id = :tenant_id
  AND order_id = :order_id
  AND line_no = :line_no;

-- Kiểm tra đúng một dòng và :new_quantity > 0.
-- Nếu không, ROLLBACK toàn bộ transaction.

COMMIT;
~~~

Tất cả đường ghi Order phải tuân theo quy tắc khóa/phiên bản chung; nếu có mã khác sửa OrderLine trực tiếp mà không kiểm tra phiên bản của root thì bất biến có thể bị phá. Tham chiếu tới Product không làm tăng phạm vi transaction của Sales sang Catalog.

## 7. Vòng đời và tính toàn vẹn của tham chiếu

Một tham chiếu có thể trở nên không truy cập được vì đối tượng nguồn bị xóa, sáp nhập, di chuyển tenant hoặc thay ID. Thiết kế cần quy định rõ hành vi:

| Tình huống | Quyết định cần có |
| --- | --- |
| Product ngừng bán | Giữ đơn cũ và snapshot; chặn hoặc điều kiện hóa đơn mới theo chính sách |
| Customer tạm khóa | Quyết định có được đặt đơn mới không; không tự xóa lịch sử đơn |
| Customer bị xóa hoặc yêu cầu xóa dữ liệu cá nhân | Phân tách thông tin cần lưu theo nghĩa vụ và thông tin cần ẩn danh/xóa; tránh cascade tùy tiện |
| Hai Customer được hợp nhất | Lưu ánh xạ ID cũ → ID chuẩn hoặc chính sách alias; xác định có cập nhật tham chiếu lịch sử hay không |
| Tham chiếu không tìm thấy khi đọc | Hiển thị snapshot hoặc trạng thái "không còn khả dụng", ghi nhận lỗi để đối soát; không tự tạo đối tượng mới |
| Một thông điệp về thay đổi đến trễ | Dùng version/sequence từ nguồn, quy tắc bỏ sự kiện cũ và cơ chế tái đồng bộ |

**Delete policy** phải được quyết định ở mức nghiệp vụ. Xóa Cascade từ Customer sang Orders thường không phù hợp nếu đơn đã chốt cần được lưu để đối soát. Trong những miền khác, entity con phụ thuộc hoàn toàn root có thể được xóa cùng root; đây là quan hệ nội bộ và có chính sách khác.

Nếu tham chiếu dùng ID từ hệ thống ngoài, nên ghi **namespace/issuer** bên cạnh ID khi có nguy cơ trùng, ví dụ (provider, providerCustomerId). Nếu đối tác thay mã, lớp tích hợp giữ bảng ánh xạ ổn định thay vì để tất cả aggregate tiêu thụ tự chuyển đổi.

## 8. Tích hợp qua hợp đồng: ID phải mang đúng ý nghĩa

Khi thông tin ở một service khác, nên thiết kế hợp đồng rõ về ID, phiên bản, thời gian và người phát hành. Ví dụ một sự kiện Catalog phát khi Product ngừng bán:

~~~json
{
  "eventId": "f64999db-d6e9-47a9-b1c4-1152798fd632",
  "eventType": "ProductDiscontinued",
  "productId": "8415699d-8119-4b28-aaf8-9e95c46c5a33",
  "tenantId": "98094b91-18cb-4be1-aa9e-a1e8ce79e594",
  "productVersion": 18,
  "occurredAt": "2026-11-20T09:00:00Z",
  "reason": "END_OF_LIFE"
}
~~~

Một Order đã xác nhận không cần tự đổi giá hoặc tên; Sales có thể xử lý sự kiện để cập nhật dữ liệu tìm kiếm/đánh dấu Product không còn đặt được. Nếu Sales có projection trạng thái Product, phải hiểu projection **có thể trễ** và không thể thay thế nguồn có thẩm quyền khi quy tắc cần quyết định ngay.

Luồng thường gặp:

~~~mermaid
sequenceDiagram
    participant S as Sales
    participant C as Catalog
    participant I as Inventory
    participant P as Payment

    S->>C: GetProduct(productId, tenantId)
    C-->>S: ProductView / quoteId / version
    S->>S: Tạo Order và lưu productId + snapshot
    S->>I: Reserve(orderId, productId, quantity, requestId)
    I-->>S: reservationId, expiresAt
    S->>P: Authorize(paymentRequestId, amount)
    P-->>S: paymentId, outcome
    S->>S: Kiểm tra kết quả, đổi trạng thái Order
~~~

Trên sơ đồ, **productId** là định danh để giao tiếp, không phải lời hứa rằng Product luôn có cùng giá. Giá phải gắn với quote/snapshot và chính sách hiệu lực; **reservationId** nhận diện quyền giữ hàng, không phải bảo đảm vĩnh viễn rằng hàng còn đó.

Để xử lý hệ thống thực tế:

- **Idempotency key** nhận diện *một yêu cầu*, khác với aggregate ID. Ví dụ hai retry của cùng lệnh thanh toán phải có cùng paymentRequestId; hai lần mua mới phải có key mới.
- **eventId** giúp bên nhận xử lý trùng; version hoặc sequence của aggregate nguồn giúp tránh áp dụng sự kiện cũ sau sự kiện mới.
- **Transactional outbox** giúp ghi trạng thái và thông điệp cần phát trong một transaction cục bộ. Bên nhận cần lưu dấu sự kiện đã xử lý (*inbox/deduplication*) nếu muốn xử lý hiệu ứng một lần ở tầng nghiệp vụ.
- Nếu một chuỗi thao tác spanning nhiều nguồn, dùng trạng thái trung gian và thao tác bù khi thất bại; không giả định có rollback xuyên service.

Thiết kế hợp đồng cần tránh một lỗi khó phát hiện: CustomerId do Customer Management phát hành và buyerId trong Sales **không nhất thiết là một loại** nếu Sales có khái niệm Buyer khác. Hai giá trị cùng kiểu UUID chưa đủ để xác nhận cùng ý nghĩa; lớp dịch tại biên (*anti-corruption layer*) có thể cần thiết.

## 9. Truy vấn nhiều aggregate mà không ghép quyền ghi

Một màn hình OrderDetail muốn hiển thị:

- Order và các dòng hàng đã chốt do Sales sở hữu;
- tên khách hiện tại do Customer sở hữu;
- ảnh sản phẩm hiện tại do Catalog sở hữu;
- tình trạng thanh toán do Payment sở hữu.

Có hai cách tiếp cận chính:

**Ghép lúc đọc:** Application/query service lấy Order theo orderId, trích customerId và tập productId, sau đó gọi API theo lô (*batch*) của Customer/Catalog. Cách này hạn chế truy vấn N+1, nhưng độ trễ và lỗi phụ thuộc các hệ thống được gọi.

**Mô hình đọc riêng (projection):** Consumer nhận sự kiện thay đổi và xây OrderDetailView gồm các trường từ nhiều nguồn. Kết quả đọc nhanh nhưng có thể trễ và cần version, thời điểm đồng bộ, xử lý sự kiện lặp/ngoài thứ tự.

| Yêu cầu đọc | Lựa chọn có thể phù hợp | Lưu ý |
| --- | --- | --- |
| Hiển thị lịch sử giao dịch chính xác | Snapshot trong Order | Không đọc lại giá hiện tại để thay giá cũ |
| Tra cứu tên khách hiện tại | Customer API hoặc projection | Chấp nhận xử lý không tìm thấy, ẩn danh và quyền riêng tư |
| Danh sách hàng nghìn Order cùng Product | Query/read model theo productId | Tránh nạp toàn bộ aggregate graph để lọc |
| Quyết định cấp quyền giữ hàng | Inventory API/command có thẩm quyền | Không dựa vào projection tồn kho có thể trễ |

Một projection phục vụ báo cáo có thể chứa cả productId và customerId nhưng không trở thành chủ sở hữu của Product hoặc Customer. **Tối ưu đường đọc không phải lý do để gộp ranh giới ghi.**

## 10. Kiểu lưu trữ không thay đổi ý nghĩa tham chiếu

| Công nghệ | Cách biểu diễn quan hệ ngoài aggregate | Rủi ro cần kiểm chứng |
| --- | --- | --- |
| **Quan hệ** | Cột customer_id, product_id; FK có chủ đích trong cùng DB | FK xuyên ngữ cảnh gây phụ thuộc xóa/migration; join không chứng minh cùng aggregate |
| **Document** | Trường customerId và các phần tử orderLines chứa productId; nhúng snapshot | Nhúng toàn bộ Customer làm dữ liệu cũ và tăng chi phí cập nhật |
| **Đồ thị** | Node Order liên hệ Customer/Product qua edge có hướng | Edge không cấp quyền sửa, không mặc định tạo transaction xuyên các root |
| **Phân tích** | FactOrderLine chứa customerKey/productKey, các dimension tương ứng | Surrogate key của warehouse có thể khác ID nguồn; cập nhật trễ và cần xử lý lịch sử |

Ví dụ một document Order:

~~~json
{
  "orderId": "835d7a89-4885-4632-8c29-6ac320ad131b",
  "tenantId": "98094b91-18cb-4be1-aa9e-a1e8ce79e594",
  "customerId": "0a99c918-fb49-41ed-8a82-6e81f2303f04",
  "recipientNameSnapshot": "Nguyen An",
  "orderLines": [
    {
      "lineNo": 1,
      "productId": "8415699d-8119-4b28-aaf8-9e95c46c5a33",
      "productNameSnapshot": "Laptop 14 inch",
      "unitPriceAmount": "23000000.00",
      "currency": "VND",
      "quantity": 1
    }
  ]
}
~~~

OrderLines là phần **bên trong** aggregate Order nên việc nhúng chúng có thể thuận tiện nếu hệ quản trị hỗ trợ cập nhật nguyên tử phù hợp. Customer vẫn được tham chiếu bằng ID; tên người nhận đã chốt là snapshot. Đổi từ quan hệ sang document không tự biến Customer thành thành viên Order.

Trong kho phân tích, khóa thay thế (surrogate key) của dimension có thể khác customerId gốc để quản lý lịch sử thay đổi. Phải giữ đường ánh xạ từ source ID và phạm vi của nó sang dimension key, tránh nhầm một ID nguồn với một ID nội bộ của warehouse.

## 11. Quy trình thiết kế một tham chiếu xuyên aggregate

Khi gặp quan hệ "A liên quan B", lần lượt trả lời:

1. **A và B có vòng đời độc lập không?** Nếu có, nhiều khả năng là hai aggregate; không kết luận chỉ từ ERD.
2. **A cần biết gì về B?** Chỉ cần nhận diện, cần snapshot lịch sử hay cần dữ liệu hiện tại?
3. **ID thuộc loại gì?** Root ID, business code, composite key theo tenant hay ID hệ thống đối tác?
4. **Ai có quyền cấp/sửa/xóa B?** Đường ghi phải đi qua root hoặc service sở hữu B.
5. **Khi nào tham chiếu phải hợp lệ?** Lúc tạo nháp, lúc xác nhận, trong suốt vòng đời hay chỉ khi đọc?
6. **Điều gì xảy ra nếu B thay đổi/biến mất?** Chặn thao tác mới, giữ snapshot, ẩn danh, lưu tombstone, hoặc đối soát?
7. **Ràng buộc nào cần nhất quán ngay?** Dùng constraint/transaction tại nguồn có thẩm quyền; thiết kế giao thức nếu xuyên hệ thống.
8. **Làm sao kiểm chứng?** Thử ID sai tenant, đối tượng không tồn tại, xóa trong lúc xác nhận, retry, event trễ và đọc khi nguồn tạm thời lỗi.

Kết quả mong đợi là một **hợp đồng tham chiếu** ngắn gọn:

| Thuộc tính hợp đồng | Ví dụ |
| --- | --- |
| Nguồn của ID | Catalog cấp ProductId |
| Phạm vi duy nhất | (tenantId, productId) |
| Bên lưu tham chiếu | Sales/OrderLine |
| Dữ liệu đi kèm | productNameSnapshot, unitPriceSnapshot |
| Kiểm tra khi ghi | Product thuộc tenant, đang được phép mua theo chính sách áp dụng |
| Khi nguồn bị xóa/ngừng hoạt động | Giữ lịch sử đơn; chặn mua mới nếu không hợp lệ |
| Quy tắc đọc | Lịch sử từ snapshot; thuộc tính hiện tại lấy từ Catalog hoặc projection |

Viết hợp đồng như vậy giúp nhóm phát triển, QA và DBA cùng hiểu ý nghĩa của cột ID, thay vì tự suy rằng chỉ cần tạo quan hệ khóa ngoại là đủ.

## 12. Bài tập thực hành: hệ thống thư viện nhiều chi nhánh

**Tình huống:** Một hệ thống thư viện có Member, BookCatalog, PhysicalCopy và Loan. Một đầu sách có nhiều bản sao vật lý; một bản sao chỉ được cho mượn bởi một lượt Loan còn hiệu lực tại một thời điểm. Độc giả có thể đổi tên, đầu sách có thể đổi tiêu đề hoặc bị gỡ khỏi danh mục, nhưng giao dịch mượn cũ phải đối soát được. Hệ thống gồm nhiều chi nhánh có mã bản sao trùng nhau.

**Yêu cầu:**

1. Đề xuất root cho Member, BookCatalog, PhysicalCopy và Loan. Quan hệ nào nên lưu ID của root khác? Quan hệ nào có thể là thành viên bên trong một aggregate?
2. Chọn định danh đầy đủ cho PhysicalCopy trong hệ thống nhiều chi nhánh; giải thích nguy cơ nếu chỉ dùng copyNo.
3. Khi tạo Loan, dữ liệu nào cần giữ snapshot và dữ liệu nào nên được tra cứu hiện hành?
4. Viết bất biến "một PhysicalCopy không có hai Loan đang hiệu lực" và đề xuất cách bảo vệ trước hai request đồng thời.
5. Nếu BookCatalog bị gỡ sau khi sách đã được mượn, Loan cũ nên xử lý thế nào?

**Một hướng giải:**

- Member có memberId; BookCatalog có bookId; PhysicalCopy có copyId theo namespace chi nhánh hoặc (branchId, copyNo); Loan có loanId. Loan lưu memberId, copyId và snapshot tiêu đề/tên người mượn theo chính sách lưu lịch sử, không nhúng đối tượng Member/BookCatalog để có thể chỉnh sửa chúng từ Loan.
- Một bản sao cụ thể có thể được nhận diện bằng (branchId, copyNo) nếu copyNo chỉ duy nhất trong chi nhánh. Nếu hệ thống cấp copyId toàn cục thì phải xác định cơ chế bảo đảm tính duy nhất thực sự, không chỉ do ứng dụng mong đợi.
- Loan lưu ngày mượn, hạn trả, chi nhánh và điều kiện giao dịch. Ảnh bìa/số điện thoại hiện hành là dữ liệu đọc tùy mục đích; tên/tiêu đề tại thời điểm mượn có thể cần snapshot theo yêu cầu pháp lý và nghiệp vụ.
- Nguồn có thẩm quyền về quyền cho mượn phải thực hiện **một thao tác nguyên tử** khi cấp bản sao. Nếu Loan và CopyAvailability cùng một database, có thể dùng UNIQUE có điều kiện đối với bản ghi đang mở kết hợp transaction, hoặc cập nhật trạng thái Copy có điều kiện. Một SELECT "bản sao đang rảnh" rồi INSERT không khóa có thể dẫn tới hai Loan hợp lệ theo từng request nhưng xung đột toàn cục.
- Khi BookCatalog bị gỡ, không xóa Loan lịch sử theo chuỗi cascade. Giữ ID hoặc tombstone cần thiết, snapshot đã cam kết và chính sách ẩn danh khi phù hợp.

Để kiểm chứng, mô phỏng hai độc giả cùng mượn bản sao cuối, Member đổi tên khi Loan còn hiệu lực, BookCatalog bị xóa và bản sao chuyển chi nhánh. Nếu mô hình không giải thích được ID nào giữ nguyên, nơi nào có quyền ghi và thao tác nào phải nguyên tử, cần xem lại ranh giới.

## 13. Các lỗi phổ biến và checklist

| Lỗi thiết kế | Tác hại | Cách khắc phục |
| --- | --- | --- |
| Order chứa Customer object và sửa trực tiếp | Bỏ qua quyền sở hữu, có thể đổi dữ liệu của đơn khác | Giữ customerId, chỉ sửa Customer qua root của Customer |
| Chỉ giữ productId, không lưu giá mua | Đơn lịch sử đổi nghĩa khi Catalog sửa giá | Lưu ID và snapshot theo thời điểm chốt |
| Coi FK là bằng chứng đủ cho quy tắc nghiệp vụ | Hàng tồn tại nhưng có thể khóa/ngừng bán | Kiểm tra điều kiện nghiệp vụ và phiên bản/hiệu lực |
| Bỏ tenantId khỏi khóa/truy vấn | Nhầm tham chiếu xuyên tổ chức và rò rỉ dữ liệu | Mang namespace đầy đủ và kiểm quyền |
| Dùng business code dễ đổi làm ID ổn định mà không có chính sách | Khi đổi mã mất liên kết | Chọn ID ổn định hoặc quy trình alias/migration |
| Xóa cascade dữ liệu lịch sử của aggregate khác | Mất khả năng đối soát và vi phạm vòng đời | Quy định delete policy, tombstone/ẩn danh |
| Dựa vào bản sao đọc trễ để xác nhận giao dịch mạnh | Chấp nhận giá/chỗ/trạng thái không còn hiệu lực | Kiểm tra tại nguồn có thẩm quyền với hợp đồng phù hợp |
| Retry lệnh tích hợp bằng ID mới mỗi lần | Có thể giữ hàng/thanh toán nhiều lần | Dùng idempotency key ổn định cho cùng yêu cầu |

Trước khi chốt lược đồ, hãy kiểm tra:

- Có rõ ID đang trỏ tới **aggregate root** nào, thuộc bounded context và namespace nào không?
- Có phân biệt ID gốc với business code và với idempotency/event ID không?
- Những trường lịch sử đã lưu snapshot đúng thời điểm cần bảo toàn chưa?
- Ai kiểm tra sự tồn tại, trạng thái, phiên bản và quyền truy cập của đối tượng được tham chiếu?
- Ràng buộc toàn vẹn nào được FK/UNIQUE/CHECK bảo vệ, ràng buộc nào cần transaction hoặc giao thức liên hệ thống?
- Khi nguồn đổi, xóa, mất liên lạc hoặc phát sự kiện trễ, hệ thống có hành vi được định nghĩa và đối soát được không?
- Truy vấn đọc nhiều aggregate có tránh N+1, có độ trễ chấp nhận được và không trở thành đường ghi tắt không?

**Kết luận:** Tham chiếu bằng định danh cho phép các aggregate **liên kết mà vẫn giữ danh tính, vòng đời và quyền thay đổi độc lập**. Thiết kế tốt phải xác định ID thuộc phạm vi nào, lúc nào cần kiểm tra, dữ liệu nào là snapshot, bất biến nào thuộc nguồn nào và cơ chế nào bảo đảm chúng. Khi hiểu rõ điều đó, khóa, chỉ mục, lược đồ và hợp đồng tích hợp mới phục vụ đúng mô hình nghiệp vụ, dù hệ thống sử dụng cơ sở dữ liệu quan hệ, document, đồ thị hay kho phân tích.
