# Module identifier và module name thường có cardinality thấp

## Mục tiêu học tập

Trong chương **Cardinality** của học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, ta tìm hiểu vì sao hai nhãn `module.identifier` và `module.name` thường là lựa chọn phù hợp để phân loại metrics và traces của ứng dụng Spring Boot sử dụng Spring Modulith.

Sau bài học, bạn có thể:

1. Giải thích **cardinality của metric label** và vì sao một metric name có thể tạo rất nhiều time series khác nhau.
2. Mô tả ý nghĩa của `module.identifier`, `module.name` trong **Module Entry Span** và các **application event metrics** do Spring Modulith tạo.
3. Chứng minh bằng ví dụ rằng số module hữu hạn làm cho hai thuộc tính này **thường có cardinality thấp** trong một bản triển khai.
4. Phân biệt **số giá trị duy nhất của từng tag** với **số tổ hợp tag thực sự xuất hiện**; tránh nhân hai nhãn có tương quan như những biến độc lập.
5. Ước lượng chi phí cardinality khi thêm `module.invocation-type`, event type, environment, instance, tenant hoặc business ID.
6. Nhận biết các tình huống mà cardinality vẫn tăng: module rename, nhiều release cùng chạy, tập hợp nhiều service, dữ liệu gắn nhãn sai và lưu trữ telemetry dài hạn.
7. Thiết kế dashboard, quy tắc cảnh báo và bước kiểm chứng để khai thác metadata module mà không đưa dữ liệu nhạy cảm hoặc giá trị không giới hạn vào metric tags.

**Phạm vi:** Spring Modulith giúp tài liệu hóa ranh giới application module bằng module graph và Actuator, đồng thời quan sát các tương tác runtime qua Micrometer, event metrics, tracing và context propagation. Bài học tập trung vào **độ đa dạng của các giá trị nhãn** trong chuỗi metrics; cách áp dụng low/high cardinality còn phụ thuộc phiên bản framework, registry, exporter và backend giám sát cụ thể.

---

## 1. Cardinality là gì?

Trong hệ thống metrics, một **time series** thường được phân biệt bằng:

- tên phép đo (**metric name**), ví dụ `module.events.published`;
- tập các cặp **key=value** của metric tags, ví dụ `module.identifier=orders` và `module.name=Orders`;
- đôi khi có các nhãn bổ sung do hạ tầng gắn vào, như `service`, `environment`, `instance`, `cluster`.

Ví dụ ba dòng sau là ba series phân biệt của cùng một tên metric vì tổ hợp tag khác nhau:

~~~text
module.events.published{module.identifier="orders",module.name="Orders"}
module.events.published{module.identifier="inventory",module.name="Inventory"}
module.events.published{module.identifier="payments",module.name="Payments"}
~~~

**Cardinality của một tag** là số lượng giá trị khác nhau mà tag đó có thể nhận trong tập dữ liệu đang xét. Chẳng hạn, với ba series trên:

- cardinality của `module.identifier` là **3**;
- cardinality của `module.name` là **3**;
- số tổ hợp hai tag đã thực sự quan sát được là **3**, không phải 3 × 3 = 9.

**Cardinality của phép đo theo bộ nhãn** là số tổ hợp khác nhau thực sự được tạo cho cùng một metric name trong một phạm vi thời gian và tập nguồn dữ liệu được xác định. Số lượng này quan trọng đối với việc lưu trữ, lập chỉ mục và truy vấn metrics backend.

### 1.1. Low cardinality và high cardinality

Micrometer Observation phân loại key-values thành hai nhóm:

| Nhóm | Đặc điểm | Ví dụ phù hợp |
| --- | --- | --- |
| **Low-cardinality key-values** | Có tập giá trị **hữu hạn, được kiểm soát** trong phạm vi vận hành mong đợi. | `module.identifier`, `module.name`, `module.invocation-type`, `result=SUCCESS/ERROR`. |
| **High-cardinality key-values** | Có thể có rất nhiều giá trị, thường thay đổi theo request, thực thể hoặc method. | `orderId`, `customerId`, `traceId`, URL có ID động; `module.method` được Spring Modulith phân loại ở nhóm high-cardinality observation keys. |

Theo tài liệu Micrometer, **chỉ low-cardinality key-values được dùng làm meter tags** trong các handler metrics tiêu chuẩn của Observation API. High-cardinality key-values không được đưa vào meters theo cơ chế đó để tránh bùng nổ số series. Tracing có thể khai thác một số high-cardinality attributes khi hạ tầng cho phép.

Điều này **không có nghĩa** cứ đánh dấu high-cardinality là có thể đưa dữ liệu nhạy cảm vào hệ thống. Trace attributes cũng cần giới hạn lưu trữ, phân quyền và chính sách xử lý dữ liệu.

### 1.2. Cardinality phụ thuộc phạm vi đang đo

Một câu “tag có cardinality bằng 8” chỉ có ý nghĩa khi nói rõ:

- Ở **một instance** hay toàn bộ service?
- Trong **một bản phát hành** hay nhiều năm release?
- Trên **một metric name** hay toàn bộ các metric?
- Với **một environment** hay hàng chục environment?
- Trong một cửa sổ 5 phút hay toàn bộ retention?

Ví dụ, một ứng dụng hiện chỉ có tám module; sau một năm đổi tên và bổ sung module, backend lưu lịch sử có thể đã thấy hai mươi tên kỹ thuật khác nhau. Điều đó vẫn có thể là cardinality thấp so với request ID, nhưng không đồng nghĩa hai con số ở mọi thời điểm đều bằng tám.

## 2. Spring Modulith xác định hai nhãn này như thế nào?

Spring Modulith nhận diện **application module** từ cấu trúc và quy tắc cấu hình của ứng dụng. Một ứng dụng thương mại điện tử có thể được chia thành:

~~~text
com.example.shop
├── orders
├── inventory
├── payments
├── shipping
└── catalog
~~~

Trong một ứng dụng có cấu trúc module ổn định, số module là một tập hữu hạn do **mã nguồn và cấu hình module detection** quyết định, khác với số đơn hàng hoặc số người dùng có thể tăng mỗi ngày.

### 2.1. Ý nghĩa của `module.identifier`

`module.identifier` biểu diễn **định danh kỹ thuật của application module** được Spring Modulith nhận diện. Với ví dụ trên:

~~~text
orders
inventory
payments
shipping
catalog
~~~

Đây là các giá trị mang ý nghĩa kiến trúc, thích hợp để lọc câu hỏi:

- Trong module nào có các lời gọi đang chậm?
- Module nào đã phát các domain events được instrumentation ghi nhận?
- Có module mới hoặc module bị đổi tên sau bản phát hành vừa rồi không?

Định danh kỹ thuật này **không phải**:

- business ID như `orderId` hoặc `paymentId`;
- trace ID hoặc span ID;
- một ID mới được tạo cho mỗi request;
- khóa được bảo đảm bất biến qua mọi refactor của ứng dụng.

Một refactor có thể thay đổi identifier nếu cách nhận diện hoặc tên module thay đổi. Vì vậy nên coi identifier ổn định **trong phiên bản và chính sách module detection đã xác định**, thay vì cam kết bất biến vĩnh viễn.

### 2.2. Ý nghĩa của `module.name`

`module.name` là **tên module** được đưa vào thông tin quan sát để đọc và phân nhóm. Nó thường liên hệ với cùng tập application modules mà identifier đại diện.

Ví dụ:

| `module.identifier` | `module.name` minh họa |
| --- | --- |
| `orders` | `Order Management` |
| `inventory` | `Inventory` |
| `payments` | `Payments` |
| `shipping` | `Shipping` |
| `catalog` | `Product Catalog` |

Tên hiển thị có thể khác identifier và có thể đổi vì cách diễn đạt nghiệp vụ. Điều đó làm nó phù hợp cho dashboard nhưng **không nên dùng tên hiển thị làm business key bền vững** để liên kết dữ liệu từ nhiều hệ thống qua thời gian, trừ khi đội phát triển sở hữu một quy tắc định danh riêng.

### 2.3. Tài liệu Spring Modulith xếp vào nhóm low-cardinality

Theo tài liệu Spring Modulith:

- Module Entry Span mang các keys `module.identifier`, `module.name`, `module.invocation-type` và `module.method`.
- Enum `ModulithObservations.LowKeys` mô tả `MODULE_IDENTIFIER`, `MODULE_NAME` và `INVOCATION_TYPE`.
- `module.method` được mô tả trong nhóm key có cardinality cao cho module observations.
- Metric tổng hợp `module.events.published` có các low-cardinality keys `module.event.type`, `module.identifier` và `module.name`.
- Metric riêng theo event type cũng có các key `module.identifier` và `module.name`, có thể được tùy biến thêm bằng application event metrics customizer.

**Điểm cần phân biệt:** “được framework xếp vào low-cardinality” là **quy ước instrumentation** phản ánh cấu trúc ứng dụng thông thường. Nó không phải một bằng chứng toán học rằng bất kỳ giá trị nào ứng dụng gắn vào key này cũng luôn ít và ổn định.

## 3. Vì sao hai nhãn thường có cardinality thấp?

Có ba nguyên nhân:

1. **Tập module gắn với kiến trúc, không gắn với từng giao dịch.** Thêm một order, một payment hoặc một request không làm ứng dụng tự có thêm một application module.
2. **Số module thường thay đổi qua release, không theo traffic.** Tăng số request từ 100 lên 1.000.000 vẫn đi qua cùng một tập module ở bản build đang chạy, nếu kiến trúc không đổi.
3. **Identifier và name thường tương quan mạnh.** Một module kỹ thuật thường có một tên hiển thị tại một thời điểm, nên số tổ hợp `(module.identifier, module.name)` gần bằng số module chứ không phải tích của hai cardinality độc lập.

### 3.1. Số module và số sự kiện là những đại lượng rất khác

Ví dụ một ứng dụng có:

- 8 application modules;
- 250.000 đơn hàng/ngày;
- 500.000 application event publications/ngày;
- 40.000 người dùng hoạt động/ngày.

Khi gắn `module.identifier` vào metric publication:

- số **lần đo** có thể tăng theo số event;
- số **giá trị identifier khác nhau** vẫn thường nằm trong tập 8 module;
- số **time series theo nhãn module** không cần tăng thành 500.000 nếu không có nhãn động khác.

Counter trong mỗi series có thể tăng từ 0 lên số rất lớn; giá trị counter lớn **không làm tăng cardinality**. Cardinality tăng khi số **bộ nhãn khác nhau** tăng.

### 3.2. Tên module có thể đổi nhưng vẫn thuộc tập nhỏ

Giả sử release đầu:

~~~text
module.identifier=orders
module.name=Orders
~~~

Release sau đổi tên hiển thị:

~~~text
module.identifier=orders
module.name=Order Management
~~~

Trong một thời điểm chỉ có một release, một identifier có thể gắn với một name. Nhưng nếu backend lưu cả hai release, nó sẽ thấy hai bộ nhãn:

~~~text
(orders, Orders)
(orders, Order Management)
~~~

Cardinality theo thời gian đã tăng thêm một chút, nhưng về bản chất vẫn bị giới hạn theo **số tên module mà ứng dụng đã sử dụng**, không tăng theo request.

Vì vậy kết luận đúng là: **module identifier và module name thường có cardinality thấp trong phạm vi một bản triển khai; cần theo dõi thay đổi khi tổng hợp nhiều release và service**.

## 4. Tính số series đúng: không nhân máy móc mọi cardinality

Một sai lầm thường gặp là thấy 8 identifier và 8 name rồi dự đoán 64 bộ nhãn. Điều đó chỉ là một **giới hạn trên** khi hai tập có thể kết hợp tùy ý; trong kiến trúc thực tế hai nhãn có quan hệ ánh xạ theo module.

Giả sử 8 module, mỗi module có một identifier duy nhất và một name:

| Module | identifier | name | Cặp thực tế |
| --- | --- | --- | --- |
| 1 | `orders` | `Orders` | 1 |
| 2 | `payments` | `Payments` | 1 |
| 3 | `inventory` | `Inventory` | 1 |
| 4–8 | Các module còn lại | Các tên tương ứng | 5 |

Ta có:

\[
|\mathrm{identifiers}|=8,\quad |\mathrm{names}|=8,\quad
|\mathrm{pairs}|=8.
\]

**Không có 64 cặp** nếu mỗi identifier tại một thời điểm chỉ đi với một name.

### 4.1. Khi thêm invocation type

Giả sử mỗi module có thể được đi vào qua hai loại invocation: `bean` và `event listener`. Trong trường hợp **mọi module đều phát sinh đủ cả hai loại**, số tổ hợp tối đa cho một observation name là:

\[
8\ \text{module pairs}\times 2\ \text{invocation types}=16.
\]

Nếu chỉ có 3 module có event listener, số tổ hợp thực còn ít hơn 16.

Tuy nhiên, việc một backend có bao nhiêu series thật còn phụ thuộc vào:

- tên meter/observation được tạo;
- tag nào thực sự được chuyển thành metric label;
- sample hoặc path nào đã chạy;
- các nhãn common tags, resource labels và instance labels đi kèm;
- cách backend chuẩn hóa tên và tag.

### 4.2. Khi thêm môi trường và instance

Giả sử:

- 8 module;
- tối đa 2 invocation types trên mỗi module;
- 3 environment;
- 5 instance trên mỗi environment.

Nếu mọi tổ hợp đều xuất hiện và cùng một metric name, **giới hạn trên minh họa** là:

\[
8\times 2\times 3\times 5=240\ \text{series}.
\]

Đây chỉ là ví dụ tính với các tổ hợp đầy đủ. Trong thực tế instance có thể không tạo cùng loại meter, backend có thể đặt instance/namespace ở tầng khác hoặc thiếu một số tổ hợp.

Để ước lượng đúng, cần **đếm bộ nhãn được tạo trong pipeline thật**, không chỉ nhân số giá trị mỗi tag.

### 4.3. Khi thêm orderId

Giả sử trên mỗi module có 100.000 orderId khác nhau và ứng dụng gắn `orderId` làm một **low-cardinality metric tag**. Nếu tất cả kết hợp xảy ra, số series có thể tăng theo hàng trăm nghìn hoặc nhiều hơn.

Đây là sự thay đổi về **bản chất cardinality**: số đơn tăng theo nghiệp vụ, trong khi số module thường tăng theo thiết kế và release.

| Nhãn | Nguồn tạo giá trị | Xu hướng cardinality |
| --- | --- | --- |
| `module.identifier` | Mô hình application module | Thường thấp và giới hạn theo kiến trúc. |
| `module.name` | Tên module | Thường thấp, có thể tăng sau rename/release. |
| `module.invocation-type` | Nhóm kiểu gọi được framework phân loại | Rất ít giá trị trong mô hình hiện tại. |
| `module.event.type` | Các kiểu application event trong mã nguồn | Thường hữu hạn, nhưng nhiều hơn số module và có thể tăng qua release. |
| `orderId` | Mỗi đơn hàng | Cao; tăng theo số giao dịch. |
| `traceId` | Mỗi trace | Rất cao, không dùng làm metric label. |
| `customerEmail` | Người dùng | Cao và nhạy cảm. |

## 5. Vị trí của các nhãn trong Spring Modulith

### 5.1. Module Entry Span

Spring Modulith có thể instrument lời gọi vào các Spring components thuộc API của application module, tạo Micrometer observations/spans cho module entry. Các key được tài liệu hóa gồm:

| Tag | Ý nghĩa |
| --- | --- |
| `module.identifier` | Định danh application module được đi vào. |
| `module.name` | Tên application module. |
| `module.invocation-type` | Loại điểm vào, ví dụ “bean” hoặc “event listener”. |
| `module.method` | Method đã được thực thi tại điểm instrument. |

Trong các observation keys được Spring Modulith công bố, ba key đầu là nhóm low-cardinality; `module.method` thuộc nhóm high-cardinality.

Một ví dụ span được mô tả dưới dạng **giả lập**:

~~~yaml
name: "inventory module entry"
attributes:
  module.identifier: inventory
  module.name: Inventory
  module.invocation-type: bean
  module.method: InventoryFacade.reserve
durationMs: 17
~~~

Đây **không phải** định dạng payload bắt buộc của framework. Tên span và thuộc tính thực tế phụ thuộc tracing bridge, convention, exporter và backend.

Mặc dù `module.method` cũng là một tập hữu hạn trong bytecode của bản build, Spring Modulith phân loại nó là high-cardinality observation key vì số lượng method và biến thể có thể cao hơn các chiều đo theo module. Không nên tự gắn method vào metric tag chỉ vì “mã nguồn có ít method” nếu chưa đánh giá cardinality và pipeline.

### 5.2. Event publications metric

Spring Modulith mô tả hai nhóm metric:

| Metric | Vai trò | Low-cardinality keys được tài liệu hóa |
| --- | --- | --- |
| `module.events.published` | Counter tổng hợp các event publications được quan sát. | `module.event.type`, `module.identifier`, `module.name`. |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter cho một loại event. | `module.identifier`, `module.name`; có thể gắn thêm tag cụ thể cho event. |

Ví dụ `OrderSubmitted` được phát từ luồng `orders` có thể được biểu diễn theo hướng dẫn framework với module identifier/name tương ứng.

**Cẩn thận:** Những counters này phản ánh **event publications được instrumentation ghi nhận**, không đồng nghĩa số đơn thành công, số listener đã commit hoặc số event duy nhất khi có retry. Module tags giúp phân loại nguồn quan sát, không biến metric thành sổ cái nghiệp vụ.

### 5.3. Module graph và Actuator không phải time series

Module graph hoặc `GET /actuator/modulith` cho biết **cấu trúc và quan hệ phụ thuộc** tại phiên bản ứng dụng. Chúng không phải tập metrics time series, nhưng có thể giúp đối chiếu:

- Bao nhiêu application modules được Spring Modulith nhận diện?
- Tên kỹ thuật và tên hiển thị hiện tại là gì?
- Có module mới sau refactor không?
- Những module nào được kỳ vọng xuất hiện trong span/metrics?

Nếu module có trong graph nhưng chưa thấy trong telemetry, có thể đơn giản vì đường xử lý chưa chạy, instrumentation chưa bao phủ, sampling hoặc exporter; không tự suy ra module không tồn tại.

## 6. Sơ đồ: module graph ổn định, metrics có lượng sự kiện lớn

~~~mermaid
flowchart TB
    subgraph STRUCT["Một bản build Spring Boot"]
        O["orders"]
        P["payments"]
        I["inventory"]
        S["shipping"]
    end
    O -->|"publish OrderSubmitted"| E1["Nhiều event publications"]
    P -->|"publish PaymentCaptured"| E2["Nhiều event publications"]
    I -->|"publish StockRejected"| E3["Nhiều event publications"]
    E1 --> MET["Micrometer metrics"]
    E2 --> MET
    E3 --> MET
    MET --> TAG["module.identifier, module.name"]
    TAG --> TS["Tập series theo module có giới hạn"]
    E1 -.-> ID["orderId, eventId thay đổi theo giao dịch"]
    ID -.-> WARN["Không đưa ID động vào low-cardinality metric tags"]
~~~

Sơ đồ nhấn mạnh: **lượng event có thể rất lớn nhưng tập module của bản build thường nhỏ và ổn định**. Chỉ các event được instrument, chuyển thành metric và lưu thành công mới xuất hiện trong backend; số lượng quan sát có thể chịu ảnh hưởng pipeline và cấu hình.

## 7. Khi nào nhận định “cardinality thấp” không còn đủ?

Các nhãn module không tự an toàn trong mọi bối cảnh. Một số ngoại lệ cần quản lý:

### 7.1. Nhiều service đẩy dữ liệu vào cùng một backend

Giả sử có 50 service, mỗi service có 10 application modules. Tập module identifier **toàn backend** có thể chứa hàng trăm giá trị. Nếu nhiều service dùng lại tên như `orders`, việc gắn `service.name` là cần thiết để phân biệt nguồn.

Cardinality của bộ nhãn `(service.name, module.identifier)` lúc đó phụ thuộc **số cặp thực tế**, không chỉ số identifier duy nhất trên tất cả service.

Nếu không có `service.name`, phép tổng hợp `module.identifier=orders` có thể vô tình cộng số liệu từ nhiều ứng dụng khác nhau. Dữ liệu không nhất thiết sai về mặt thống kê, nhưng cách diễn giải dashboard có thể sai phạm vi.

### 7.2. Rolling deployment và nhiều release

Khi triển khai canary/rolling, hai phiên bản chạy đồng thời có thể có tên module khác nhau. Dashboard trong một giờ có thể thấy:

~~~text
release=2026.11-a, module.identifier=checkout
release=2026.11-b, module.identifier=orders
~~~

Đó có thể là **thay đổi có chủ đích về kiến trúc**, không nhất thiết lỗi observability. Cần ghi nhận revision hoặc version nguồn để giải thích khác biệt.

Một điều cần tránh là gắn **mã build duy nhất của mọi request** vào metric tags; build revision thường hữu hạn theo deployment, nhưng cũng tăng số series trong thời gian rollout và retention. Phải tính tập giá trị thực cùng nhãn môi trường/instance.

### 7.3. Tên hiển thị đổi thường xuyên

`module.name` có thể bị đổi để phù hợp thuật ngữ tổ chức. Nếu dashboard nhóm theo name và mỗi tuần đổi cách viết, lịch sử sẽ bị phân mảnh thành nhiều series.

Nên:

- Dùng `module.identifier` làm trục phân nhóm kỹ thuật khi identity ổn định trong dự án.
- Dùng `module.name` cho hiển thị khi phù hợp.
- Có mapping/migration khi đổi identifier hoặc display name.
- Review sự thay đổi module graph cùng PR/release.

Không coi tên kỹ thuật bất biến tuyệt đối: refactor hoặc thay cấu hình module detection cũng có thể đổi identifier.

### 7.4. Tự gắn giá trị động sai vào key của framework

Một custom `ModulithObservationConvention` hoặc `ObservationFilter` có thể sửa `module.name` thành một giá trị lấy từ request, ví dụ:

~~~java
// KHÔNG NÊN: biến tên module thành nhãn động theo từng đơn.
context.addLowCardinalityKeyValue(
    KeyValue.of("module.name", "orders-" + orderId)
);
~~~

Đây là **mẫu phản ví dụ**, không phải khuyến nghị. Bằng việc làm vậy, ứng dụng phá ngữ nghĩa tên module và biến tag vốn có cardinality thấp thành một tập gần như vô hạn.

Nếu cần gắn nhóm nghiệp vụ, hãy dùng **tag khác** với tập giá trị được kiểm soát, ví dụ `shop.channel=WEB|STORE|PARTNER|OTHER`. Đừng ghi đè các key framework dùng để nhận diện module.

### 7.5. Module tạo động không thuộc mô hình Spring Modulith thông thường

Trong Spring Modulith, application module thường được phát hiện từ cấu trúc mã nguồn/cấu hình của bản triển khai. Một hệ thống plugin động hoặc tenant tự định nghĩa “module” theo request sẽ có ngữ nghĩa khác. Không nên áp dụng máy móc giả định cardinality thấp của **application module framework** cho ID plugin, tenant hoặc workflow động.

### 7.6. Thêm tags không giới hạn vào metric riêng của event

`ModulithEventMetricsCustomizer` cho phép làm giàu counter theo event type, nhưng người viết customizer có thể đưa một field nhiều giá trị vào meter. Khi đó **metric vẫn có `module.identifier` cardinality thấp**, nhưng **tổng số series của metric có thể rất lớn** do một tag khác.

Vì thế, đừng kết luận “metric an toàn” chỉ vì hai trường `module.identifier` và `module.name` an toàn. Cần kiểm tra **mọi tag trên meter cuối cùng**.

## 8. Đặt tên và phạm vi phân nhóm cho dashboard

Một dashboard hữu ích có thể bắt đầu bằng những chiều sau:

| Câu hỏi | Nhãn nhóm gợi ý | Cần phân biệt |
| --- | --- | --- |
| Module nào xuất hiện nhiều ở các entry spans? | `service.name`, `module.identifier` | Số span đã quan sát chịu ảnh hưởng sampling, không phải toàn bộ số lời gọi. |
| Thời gian xử lý của từng module thế nào? | `module.identifier` và các tag còn lại được backend hỗ trợ | Duration của span/timer không phải độ trễ toàn workflow. |
| Module nào publish nhiều events? | `module.identifier`, `module.event.type` | Counter publication khác với số consumer hoàn tất. |
| Event nào tăng theo module? | `module.identifier`, loại event | Có thể có retry/duplicate publication. |
| Có thay đổi tên module sau release? | `service.name`, `module.identifier`, `module.name`, revision | Rename có thể tạo series mới; đừng nhầm với tăng traffic. |

### 8.1. Không bắt buộc giữ cả hai tag trong mọi panel

Nếu `module.identifier` và `module.name` là cặp ánh xạ gần một-một, việc giữ cả hai có thể có giá trị cho hiển thị, nhưng **không nhất thiết làm tăng số series theo tích số**.

Khi định nghĩa dashboard:

- dùng identifier để lọc kỹ thuật nếu mục tiêu là phân tích ổn định;
- dùng name cho phần trình bày cho con người nếu phù hợp;
- khi nhóm dữ liệu từ nhiều service, phải giữ định danh của service;
- khi số module lớn, sắp xếp/lọc top N để UI dễ đọc, không thay đổi ngầm ý nghĩa phép đo.

### 8.2. Đừng tự tạo “tên module” theo request

Một dashboard muốn phân nhóm theo khách hàng hoặc chiến dịch có thể bị cám dỗ biến `module.name` thành `orders-campaign-123`. Điều này làm lẫn kiến trúc với nghiệp vụ và phá khả năng liên kết module graph.

Nếu cần phân nhóm nghiệp vụ, dùng một nhãn **được định nghĩa riêng** và duy trì tập giá trị hữu hạn như:

~~~text
shop.channel=WEB
shop.channel=STORE
shop.channel=OTHER
~~~

Vẫn cần đo xem thêm nhãn này nhân số series lên bao nhiêu; không phải mọi giá trị enum đều nên thành metric tag nếu dashboard không sử dụng.

## 9. Ví dụ cấu hình ứng dụng Spring Boot

### 9.1. Bật observability của Spring Modulith

Với Gradle và BOM Spring Modulith tương thích đã được quản lý:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Starter Insight đưa vào hạ tầng liên quan Module Actuator và observability. Nếu chỉ cần instrumentation mà không cần starter đầy đủ, có thể dùng `spring-modulith-observability-core` theo hướng dẫn phiên bản đang chạy.

Maven:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

**Lưu ý:** Bật instrumentation không đồng nghĩa một tracing backend đã được cấu hình. Để xuất spans cần Micrometer tracing bridge/exporter và cấu hình thu thập tương ứng. Metrics và traces có thể có các cơ chế lưu trữ, sampling và thời hạn retention khác nhau.

### 9.2. Kiểm tra qua Actuator một cách có kiểm soát

Nếu ứng dụng đang dùng Spring Boot Actuator và muốn xem danh sách metric ở môi trường phát triển:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,modulith
~~~

Đây là **cấu hình chủ động expose**, không phải mặc định mở tất cả endpoint. Với cổng và base path mặc định, có thể thử:

~~~bash
curl --fail-with-body --silent --show-error \
  http://localhost:8080/actuator/metrics

curl --fail-with-body --silent --show-error \
  http://localhost:8080/actuator/modulith
~~~

`/actuator/modulith` cho biết thông tin **cấu trúc module**, giúp đối chiếu số lượng identifier/name. `/actuator/metrics` cho biết các meters đã được đăng ký nếu có dữ liệu. Tên meter/label trên exporter như Prometheus có thể được chuẩn hóa khác nhau.

Trong production, các endpoint quản trị phải được phân quyền và giới hạn mạng phù hợp. Metadata module có thể tiết lộ kiến trúc nội bộ; không tự expose ra công cộng.

### 9.3. Đừng tự instrument trùng module spans khi đã có framework

Ví dụ sau minh họa trực tiếp **ngữ nghĩa low-cardinality của Micrometer**, không phải cách mặc định để tái tạo module entry spans:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

void demonstrateLowCardinality(ObservationRegistry registry) {

    Observation.createNotStarted("shop.demo.module", registry)
        .lowCardinalityKeyValue("module.identifier", "inventory")
        .lowCardinalityKeyValue("module.name", "Inventory")
        .lowCardinalityKeyValue("module.invocation-type", "bean")
        .observe(() -> {
            // Công việc minh họa, cố ý lược bỏ logic nghiệp vụ.
        });
}
~~~

Vì các giá trị được chọn từ tập module hữu hạn, một metric handler tiêu chuẩn có thể tạo series được nhóm theo ba nhãn tương ứng. Tuy nhiên, mã trên **là custom observation riêng có tên `shop.demo.module`**; nó không phải module span do Spring Modulith tự phát hiện và không nên thêm vào luồng production đã được instrument chỉ để đếm trùng lời gọi.

Khi muốn dùng telemetry framework, ưu tiên các observation do Spring Modulith tạo khi lời gọi đi qua API module phù hợp.

## 10. Kiểm tra cardinality bằng dữ liệu thực

### 10.1. Bốn con số nên theo dõi

Trên hệ thống quan sát, có thể theo dõi bốn mức:

1. **Số application module thực:** lấy từ module graph/tài liệu của bản build.
2. **Số `module.identifier` riêng biệt đã xuất hiện:** theo khoảng thời gian và nguồn dữ liệu cụ thể.
3. **Số cặp `(module.identifier,module.name)`:** giúp phát hiện cùng identifier đang có nhiều name do rolling upgrade hoặc đổi cấu hình.
4. **Số series cho từng metric name và tổ hợp tất cả tags:** đây mới là yếu tố trực tiếp tác động đến metrics backend.

Một hệ thống có 12 module, 12 identifier và 13 cặp identifier/name sau đổi tên vẫn có thể hoàn toàn bình thường. Ngược lại, 12 identifier nhưng một metric có 500.000 series gợi ý **tag khác** gây bùng nổ.

### 10.2. Pseudo-query để kiểm tra

Các phép tính sau mô tả **ý tưởng**, không phải cú pháp chuẩn của PromQL, Grafana hay một backend cụ thể:

~~~text
unique_module_ids = COUNT_DISTINCT(module.identifier)

unique_module_names = COUNT_DISTINCT(module.name)

unique_module_pairs =
    COUNT_DISTINCT( (module.identifier, module.name) )

series_per_metric =
    COUNT_DISTINCT( (metric_name, all_metric_tag_values) )
~~~

Khi thực hiện, luôn thêm điều kiện `service`, `environment` và khung thời gian. Không gộp số liệu của 50 service rồi so với số module của một service.

### 10.3. Đọc các nhãn thực sự có trong MeterRegistry

Đây là một đoạn **mã chẩn đoán Java** để thống kê các cặp module đã xuất hiện trong meters hiện đang được đăng ký. Nó không trả về tất cả module trong kiến trúc, vì một module chưa phát sinh metric có thể chưa có meter.

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.Objects;
import java.util.Set;
import java.util.stream.Collectors;

class ModuleTagInspector {

    static Set<String> observedModulePairs(MeterRegistry registry) {
        return registry.getMeters().stream()
            .map(Meter::getId)
            .filter(id -> id.getTag("module.identifier") != null)
            .map(id -> id.getTag("module.identifier") + " / " +
                Objects.toString(id.getTag("module.name"), "<missing>"))
            .collect(Collectors.toSet());
    }
}
~~~

**Lưu ý khi diễn giải:**

- Đây là tập **cặp đã đăng ký trong JVM**, không phải số series đang lưu trong Prometheus hoặc backend khác.
- Các meter có thể được tạo **lười** khi luồng chạy lần đầu, nên một module chưa được gọi có thể chưa xuất hiện.
- Bộ lọc ở ví dụ lấy mọi meter mang `module.identifier`; nếu chỉ phân tích event metrics, cần lọc thêm metric name.
- Code hiển thị dữ liệu đã được framework/tagging thực sự đưa vào registry; không chứng minh spans đã xuất thành công.
- Đừng dùng inspector làm polling tần suất cao nếu registry lớn; thích hợp cho kiểm tra chẩn đoán hoặc test có kiểm soát.

### 10.4. Đối chiếu module graph với metric labels

Giả sử `/actuator/modulith` mô tả 10 module nhưng inspector chỉ thấy 6 cặp module. Những giả thuyết hợp lý:

- Bốn module không xuất hiện trong các luồng đã chạy.
- Một số module không có event publication hoặc API entry được instrument.
- Observation có thể không dẫn tới meter tương ứng do handler/cấu hình.
- Tên/keys đã bị tùy biến hoặc không được registry xuất theo cách inspector kỳ vọng.
- Tập meters mới quan sát chưa đủ thời gian hoặc ứng dụng đang dùng phiên bản khác.

Không nên tự suy ra “4 module bị mất” chỉ từ chênh lệch số cặp; cần so sánh **cùng instance, revision và phạm vi đo**.

## 11. Bảo vệ cardinality bằng thiết kế, rồi mới đến giới hạn kỹ thuật

### 11.1. Quy tắc thiết kế nên ưu tiên

- Giữ `module.identifier` là **định danh module**, không gán `orderId` hay `tenantId` vào đó.
- Dùng `module.name` theo metadata module, tránh nối chuỗi động từ request.
- Chỉ thêm những nhãn có **tập giá trị xác định** và phục vụ truy vấn/alert thật.
- Chuẩn hóa các giá trị lấy từ bên ngoài bằng enum/whitelist: `OTHER` cho giá trị lạ.
- Định nghĩa ngữ nghĩa của nhãn cùng chủ sở hữu và vòng đời phiên bản.
- Tính cardinality của **tổ hợp tất cả tags**; nhớ common tags và resource labels.
- Không đưa PII, payment token, email hay business ID duy nhất vào meter tags.

### 11.2. Ví dụ normalize một tag nghiệp vụ

Giả sử ứng dụng thêm `sales.channel` cho metric của event `OrderSubmitted`. Thay vì lấy raw String làm nhãn:

~~~java
static String safeChannel(String raw) {
    if (raw == null) {
        return "OTHER";
    }

    return switch (raw.trim().toUpperCase(java.util.Locale.ROOT)) {
        case "WEB" -> "WEB";
        case "STORE" -> "STORE";
        case "PARTNER" -> "PARTNER";
        default -> "OTHER";
    };
}
~~~

Việc chuẩn hóa đảm bảo `sales.channel` có nhiều nhất bốn giá trị theo chính sách trên. Nó không sửa metadata của `module.identifier` hay `module.name`, vốn phản ánh kiến trúc.

### 11.3. MeterFilter.maximumAllowableTags như lớp phòng vệ

Micrometer cung cấp `MeterFilter.maximumAllowableTags(...)` để giới hạn số giá trị của một tag trên nhóm meter. Ví dụ minh họa:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;

void addDefensiveLimit(MeterRegistry registry) {
    registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
            "module.events.published",
            "module.identifier",
            64,
            MeterFilter.deny()
        )
    );
}
~~~

Ví dụ giới hạn tối đa **64 giá trị khác nhau** cho `module.identifier` trên các meters có tên bắt đầu bằng tiền tố đã định. Đây là một **guardrail** trong môi trường minh họa; 64 không phải khuyến nghị mặc định cho mọi hệ thống.

**Hạn chế cần hiểu:**

- Nếu vượt ngưỡng, `MeterFilter.deny()` có thể khiến meter mới bị từ chối: bạn sẽ **mất một phần telemetry**, không giải quyết được nguyên nhân đặt nhãn sai.
- Giới hạn chỉ một tag không đảm bảo tổng số series thấp khi các tags khác có nhiều giá trị.
- Cần đăng ký filter **sớm trước khi meters được tạo** và kiểm tra cách khởi tạo MeterRegistry trong Spring Boot thực tế.
- Dùng ngưỡng theo số module dự kiến, kế hoạch mở rộng và thời gian migration; theo dõi khi cơ chế phòng vệ kích hoạt.
- Ưu tiên **sửa nguồn nhãn và normalization**, dùng meter filter làm lớp bảo vệ cuối.

Tài liệu Micrometer cũng cung cấp các công cụ quan sát/dò tag có cardinality lớn. Đây là cách bổ sung bằng chứng khi nghi ngờ series tăng bất thường.

## 12. Ước lượng ngân sách cardinality

Một quy trình đánh giá đơn giản cho một metric cụ thể:

1. Liệt kê tất cả tags có thể xuất hiện trên meter, **bao gồm tags mặc định** của Spring Modulith và các common tags do registry/exporter gắn.
2. Phân loại mỗi tag là **tập cố định**, **tập tăng theo release**, **tập tăng theo instance** hoặc **tập tăng theo business entities**.
3. Tìm các cặp tag có **quan hệ phụ thuộc**; ví dụ name thường phụ thuộc identifier trong một revision.
4. Ước lượng giới hạn trên của **số tổ hợp hợp lệ** thay vì nhân tất cả các cardinality độc lập.
5. Đo số series thực tế trên backend cùng khoảng thời gian, môi trường và metric name.
6. Đặt ngân sách và cảnh báo cho số series mới, nhãn động hoặc tốc độ tăng bất thường.
7. Khi vượt ngân sách, điều tra nhãn sinh thêm giá trị thay vì vội xóa `module.identifier`.

### 12.1. Bài toán minh họa

Một ứng dụng chạy trong 2 environment; mỗi environment có 4 instance. Mã nguồn có 12 application modules, mỗi module có 1 name; instrumentation phân loại tối đa 2 invocation types.

Giới hạn trên minh họa theo bộ nhãn `(environment,instance,module.identifier,module.name,invocation-type)` là:

\[
2\times4\times12\times2=192.
\]

Nếu thêm `sales.channel` có 4 giá trị **và mọi tổ hợp đều xuất hiện trên cùng một metric**, giới hạn trên trở thành:

\[
192\times4=768.
\]

Nhưng nếu chỉ event publication metrics có `sales.channel`, còn module invocation metrics không có tag đó, **không được áp dụng 768 cho mọi metric**. Phải tính riêng từng tên metric và bộ tags thực tế.

Nếu thêm `orderId` có 100.000 giá trị, số series có thể bùng nổ. Giải pháp là không dùng ID giao dịch làm low-cardinality tag, dù `module.identifier` và `module.name` vẫn có cardinality thấp.

## 13. Các hiểu nhầm thường gặp

### 13.1. “Cardinality thấp nghĩa là counter ít tăng”

Sai. Một series mang `module.identifier=orders` có thể đếm hàng triệu event publications. **Counter value** và **số series** là hai đại lượng khác nhau.

### 13.2. “Có 10 identifier và 10 name thì chắc chắn 100 series”

Sai. Nếu mỗi identifier ứng với một name ở bản đang chạy, chỉ có khoảng 10 **cặp hợp lệ**. Phải đếm tổ hợp thực, không nhân máy móc các tag phụ thuộc nhau.

### 13.3. “Dùng module.name làm business key là an toàn”

Không có bảo đảm. Tên module có thể đổi; tên kỹ thuật cũng có thể đổi do refactor hoặc cấu hình detection. Khi lưu lịch sử dài hạn, cần mapping và chính sách migration.

### 13.4. “Low-cardinality key không bao giờ làm tăng chi phí”

Sai. Dù chỉ có 10 giá trị, nó vẫn là một chiều phân loại. Trong tổ hợp với event type, instance, environment, trạng thái hoặc tag khác, tổng số series vẫn tăng. “Low” nghĩa là giới hạn hợp lý, **không nghĩa là miễn phí**.

### 13.5. “Nếu high-cardinality thì thêm vào metrics vì framework tự biết”

Sai. Micrometer mô tả high-cardinality metadata phục vụ quan sát như tracing; meter handlers tiêu chuẩn tránh đưa nó vào meter tags. Khi một đoạn custom code tự tạo `Counter.Builder.tags(...)` với business ID, framework không tự làm ID đó trở nên an toàn.

### 13.6. “Tất cả module đều phải có metric nếu ứng dụng healthy”

Sai. Module graph mô tả cấu trúc; metrics và spans mô tả những hoạt động đã được instrument và thu thập. Một module chưa phát event hoặc chưa có lời gọi API được quan sát có thể không xuất hiện trên dashboard.

### 13.7. “Số module spans bằng số request”

Sai. Một request có thể đi qua nhiều module hoặc sinh nhiều spans; sampling có thể làm mất dấu vết trong backend. Một event có thể được xử lý qua retry hoặc bất đồng bộ. Invocation metrics/traces không nên được diễn giải thành số giao dịch duy nhất nếu thiếu định nghĩa đo phù hợp.

### 13.8. “Bổ sung orderId vào module.name giúp điều tra dễ hơn”

Về ngắn hạn có thể thấy dữ liệu chi tiết, nhưng làm sai ý nghĩa `module.name` và gây nổ cardinality. Dùng **trace/log correlation** có phân quyền cho ID nghiệp vụ, giữ module tags để phân nhóm kiến trúc.

## 14. Tình huống xử lý sự cố: series tăng 200 lần dù số module không đổi

Giả sử một dịch vụ `shop-service` có 15 modules. Sau release mới, số active metrics series tăng gấp 200, trong khi Actuator vẫn liệt kê 15 module.

Quy trình điều tra:

1. **Xác nhận phạm vi đo:** số series của metric nào tăng, ở environment nào, trên bao nhiêu instance? Có thay đổi retention hoặc scrape target không?
2. **Xem bộ tag trước/sau release:** `module.identifier` có thêm hàng nghìn giá trị không hay vẫn khoảng 15? `module.name` có bị gắn ID động không?
3. **Kiểm tra các customizers:** `ModulithEventMetricsCustomizer` có lấy `event.orderId()`, `event.customerId()` hoặc raw input làm tag?
4. **Kiểm tra common tags và resource labels:** deployment có tăng instance hoặc thêm revision/dynamic route tag không?
5. **Tính lại số tổ hợp:** ghi nhận các tag thực sự đi cùng một metric name; không chỉ nhìn từng tag.
6. **Sửa nguồn nhãn gây tăng:** thay dữ liệu động bằng nhóm hữu hạn, bảo toàn hai module tags có ý nghĩa kiến trúc.
7. **Kiểm tra lại trên staging:** chạy những tình huống có traffic đại diện, đo số series và xác nhận dashboard/alert không bị phá nghĩa.
8. **Theo dõi sau triển khai:** series cũ có thể tiếp tục tồn tại trong retention của backend; việc sửa code không xóa ngay dữ liệu lịch sử.

### Sơ đồ quyết định

~~~mermaid
flowchart TD
    A["Series tăng bất thường"] --> B{"module.identifier có giá trị mới?"}
    B -->|"Có"| C["Kiểm tra refactor, nhiều service/release,\ncustom convention hoặc tag sai"]
    B -->|"Không"| D{"module.name có biến thể mới?"}
    D -->|"Có"| E["Kiểm tra rename, display name,\ntag được nối dữ liệu động"]
    D -->|"Không"| F["Xem tất cả tags của metric đang tăng"]
    F --> G{"Có tag theo orderId/userId/URL?"}
    G -->|"Có"| H["Bỏ ID động khỏi metric tags;\ndùng nhóm hữu hạn"]
    G -->|"Không"| I["Kiểm tra instance, release, event type,\ncommon tags và exporter"]
    C --> J["Đo lại bộ nhãn trên staging"]
    E --> J
    H --> J
    I --> J
~~~

Điểm quan trọng của tình huống: **nếu module count không đổi, nguyên nhân tăng series có thể nằm ở một tag khác**; không nhất thiết cần xóa metadata module vốn đang hữu ích.

## 15. Checklist thiết kế dashboard và metric tags

- [ ] Đã xác định metric name, nguồn dữ liệu, environment và khoảng thời gian quan sát.
- [ ] Hiểu `module.identifier` là định danh application module theo kiến trúc hiện tại.
- [ ] Hiểu `module.name` là tên module, có thể thay đổi qua release.
- [ ] Đã đối chiếu số module trong module graph/Actuator với tập module tags thu thập được.
- [ ] Đã kiểm tra hai tag có quan hệ gần một-một, tránh nhân cardinality sai.
- [ ] Đã tính thêm `module.invocation-type`, `module.event.type` và các tags thực tế khác.
- [ ] Có quy tắc tách service/environment khi nhiều ứng dụng cùng gửi telemetry.
- [ ] Đã cân nhắc rolling/canary deployments và việc đổi tên module.
- [ ] Không ghi đè `module.identifier` hoặc `module.name` bằng dữ liệu theo request.
- [ ] Không đưa `orderId`, `eventId`, `traceId`, email hoặc payment token vào metric tags.
- [ ] Có giới hạn/whitelist cho các tag nghiệp vụ do customizer thêm.
- [ ] Có phép đo số series thực tế trên backend, không chỉ ước lượng bằng lý thuyết.
- [ ] Có cảnh báo cho sự tăng bất thường của cardinality hoặc series mới.
- [ ] Nếu dùng `MeterFilter`, đã biết hệ quả **từ chối meter mới** khi vượt ngưỡng.
- [ ] Dashboard và báo cáo không diễn giải số module spans/event publications thành số nghiệp vụ hoàn tất.

## 16. Bài tập tự luyện

1. **Định nghĩa:** Một metric có 7 values cho `module.identifier` và 7 values cho `module.name`. Khi nào số bộ nhãn là 7, khi nào có thể lớn hơn 7?
2. **Tính toán:** Có 9 modules, mỗi module có một name, 2 invocation types, 3 environments. Ước lượng giới hạn trên của bộ nhãn theo ba chiều trên trong trường hợp mọi tổ hợp xuất hiện.
3. **Kỹ thuật:** Vì sao số lần `OrderSubmitted` được publish tăng từ 1.000 lên 1.000.000 không tự làm tăng cardinality của `module.identifier`?
4. **Refactor:** Release cũ dùng identifier `checkout`, release mới dùng `orders`. Cần lưu thêm dữ liệu gì để dashboard hiểu đúng thay đổi?
5. **Đọc dữ liệu:** Actuator có 12 modules nhưng metrics chỉ hiển thị 8 module identifiers. Hãy nêu ít nhất bốn lý do hợp lý.
6. **Thiết kế tag:** Một kỹ sư gắn `orderId` vào `module.name` để phân biệt giao dịch. Hãy viết phản biện về semantics, cardinality, bảo mật và cách thay thế.
7. **Đo lường:** Hệ thống có nhiều service đều có module `payments`. Dashboard chỉ lọc `module.identifier=payments`; dữ liệu có thể bị hiểu sai như thế nào?
8. **Ngân sách:** Một metric event có 10 modules, 5 event types và một tag `sales.channel` có 4 values. Hãy tính giới hạn trên khi mọi tổ hợp hợp lệ, sau đó giải thích tại sao giới hạn này có thể lớn hơn số series thực.
9. **Đối chiếu:** Khi `module.name` đổi qua hai bản phát hành nhưng `module.identifier` giữ nguyên, cardinality của từng tag và cặp tag sẽ biến đổi thế nào trong retention gồm cả hai bản?
10. **Giới hạn bảo vệ:** `MeterFilter.maximumAllowableTags(...)` có thể ngăn việc tạo meter mới khi quá ngưỡng. Vì sao đây là lớp phòng vệ cuối cùng và cần có cảnh báo khi bị kích hoạt?
11. **Traces:** Vì sao `module.method` nằm trong nhóm high-cardinality của Module Entry Span, dù số method trong một bản build cũng hữu hạn?
12. **Nghiệp vụ:** Vì sao metrics có `module.identifier=payments` và `module.name=Payments` không đủ chứng minh thanh toán đã commit hoặc không bị xử lý hai lần?

## 17. Tổng kết

`module.identifier` và `module.name` **thường có cardinality thấp** vì giá trị của chúng đi theo **tập application module được định nghĩa bởi kiến trúc ứng dụng**, thay vì đi theo từng request hoặc business entity. Trong một bản triển khai, mỗi identifier thường tương ứng một name nên số cặp giá trị thực tế gần bằng **số module**, không phải tích của hai tập giá trị độc lập.

Đây là lý do Spring Modulith đặt chúng vào nhóm **low-cardinality keys** cho Module Entry observations và event publication metrics. Chúng giúp phân tích tương tác giữa modules, kiểm tra module graph và phân loại telemetry bằng các nhãn có ý nghĩa kiến trúc.

Tuy nhiên, low cardinality **không bảo đảm tổng số series thấp** nếu ứng dụng thêm tags động, trộn nhiều service, nhiều release hoặc dùng custom convention ghi đè identifier/name sai ý nghĩa. Cần tính **tổ hợp labels thực tế**, kiểm soát các tag nghiệp vụ, theo dõi cardinality trên backend và giữ các business IDs trong cơ chế correlation phù hợp thay vì metric labels.

### Tài liệu tham khảo

1. [Spring Modulith — Production-ready Features: Observability Spans, Event Metrics và Low Cardinality Keys](https://docs.spring.io/spring-modulith/reference/production-ready.html).
2. [Spring Modulith Javadoc — ModulithObservations.LowKeys](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.LowKeys.html).
3. [Spring Modulith Javadoc — ModulithObservations.HighKeys](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.HighKeys.html).
4. [Micrometer — Observation Introduction: low và high cardinality](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).
5. [Micrometer — Observation Components: metric handlers và key-values](https://docs.micrometer.io/micrometer/reference/observation/components.html).
6. [Micrometer — High Cardinality Tags Detector và MeterFilter](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html).
7. [Spring Boot — Metrics và Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
