# Chọn lưu trạng thái hiện tại, lịch sử thay đổi hay cả hai

## 1. Bài toán: cần biết điều gì về dữ liệu theo thời gian?

Trong **DATABASE_DATA_MODELING**, việc chuyển yêu cầu nghiệp vụ thành lược đồ dữ liệu không dừng ở việc xác định thực thể, quan hệ, khóa và chỉ mục. Ta còn phải quyết định **dữ liệu có ý nghĩa tại thời điểm nào** và **hệ thống cần trả lời câu hỏi về quá khứ đến mức nào**. Một thiết kế phục vụ tốt màn hình hiện tại chưa chắc chứng minh được vì sao một đơn hàng được hoàn tiền, mức giá nào đã áp dụng hoặc địa chỉ giao hàng nào từng được xác nhận.

Xét đơn hàng số 42 với chuỗi trạng thái:

~~~text
10:00  NEW       (được tạo)
10:03  PAID      (đã thanh toán)
10:15  PACKED    (đã đóng gói)
11:20  SHIPPED   (đã bàn giao vận chuyển)
~~~

Ba câu hỏi tạo ra ba yêu cầu lưu trữ khác nhau:

- **“Bây giờ đơn hàng đang ở trạng thái nào?”** Cần trạng thái hiện tại: SHIPPED.
- **“Lúc 10:10 đơn hàng ở trạng thái nào và đã đi qua các bước gì?”** Cần dữ liệu lịch sử có thể truy vấn theo thời điểm.
- **“Hôm qua hệ thống tin điều gì về một sự kiện xảy ra từ tuần trước?”** Cần phân biệt thời điểm sự kiện có hiệu lực và thời điểm hệ thống biết/ghi nhận sự kiện; đôi khi cần mô hình hai trục thời gian (*bitemporal*).

**Trạng thái** là giá trị mô tả thực thể ở một thời điểm (ví dụ trạng thái đơn hàng, hạng thành viên). **Lịch sử trạng thái** ghi các phiên bản giá trị qua thời gian. **Sự kiện nghiệp vụ** diễn tả điều đã xảy ra (ví dụ “Thanh toán thành công”, “Đơn bị hủy theo yêu cầu khách”), có thể mang nhiều thông tin hơn một giá trị trạng thái. Không phải nhật ký ứng dụng, log HTTP, thông báo CDC hay bảng audit nào cũng đủ để tái dựng lịch sử nghiệp vụ chính xác.

Quyết định mô hình hóa phải xuất phát từ câu hỏi nghiệp vụ, thời gian lưu giữ, nhu cầu đối soát, cách sửa sai, tần suất ghi/đọc và mức nhất quán mong muốn; không có lựa chọn luôn đúng cho mọi thực thể.

## 2. Ba phương án cốt lõi

| Phương án | Lưu gì? | Truy vấn tốt nhất | Đánh đổi chính | Tình huống phù hợp |
|---|---|---|---|---|
| **Chỉ trạng thái hiện tại** (*current state*) | Một bản ghi hoặc tài liệu chứa giá trị mới nhất; cập nhật ghi đè | Tra cứu nhanh “bây giờ là gì?” | Không tự trả lời được “trước đây là gì?”; không có dấu vết thay đổi đáng tin cậy | Giỏ hàng tạm, cấu hình có thể thay thế, giá trị cache có thể tái tạo |
| **Chỉ lịch sử** (*history as source of truth*) | Dãy phiên bản hoặc sự kiện bất biến theo thực thể, có thứ tự | Tái dựng diễn biến, truy vấn quá khứ, phân tích nguyên nhân | Muốn biết hiện tại phải chọn bản mới nhất hoặc dựng lại trạng thái; truy vấn và vận hành phức tạp hơn | Sổ cái, quy trình cần truy vết đầy đủ, hệ thống lấy sự kiện làm nguồn sự thật |
| **Cả hiện tại và lịch sử** (*current + history*) | Bản ghi hiện tại để đọc nhanh, cùng bảng lịch sử để truy vết | Cả màn hình thời gian thực lẫn điều tra, đối soát | Tốn dung lượng và phải giữ hai biểu diễn nhất quán | Trạng thái đơn hàng, gói thuê bao, quyền hạn, giá niêm yết có yêu cầu truy vết |

Đừng đánh đồng “chỉ lịch sử” với **event sourcing**: bảng phiên bản đầy đủ có thể lấy bản gần nhất, còn event sourcing lưu sự kiện miền và dùng logic xử lý để tái dựng trạng thái. Cũng đừng coi “cả hai” là hai nguồn sự thật độc lập: cần chỉ rõ nguồn nào có thẩm quyền, biểu diễn nào là bản sao hoặc cách cập nhật nguyên tử để không lệch nhau.

### 2.1. Chỉ lưu trạng thái hiện tại

~~~sql
CREATE TABLE shopping_cart_item (
    cart_id      bigint NOT NULL,
    product_id   bigint NOT NULL,
    quantity     integer NOT NULL CHECK (quantity > 0),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (cart_id, product_id)
);
~~~

Mỗi lần thay đổi số lượng, hàng cũ được cập nhật; thiết kế này hợp lý nếu nghiệp vụ chỉ cần giỏ hàng đang có, không có yêu cầu điều tra từng lần tăng giảm. Trường **updated_at** cho biết lần cập nhật gần nhất, **không** cho biết các giá trị cũ. Nếu giỏ hàng đã thành đơn hàng, dữ liệu đơn cần được chốt riêng để giá và số lượng về sau không làm thay đổi giao dịch đã xác nhận.

**Ưu điểm:** cấu trúc và giao dịch đơn giản, dung lượng nhỏ, dễ tạo khóa duy nhất, dễ lập chỉ mục theo truy vấn hiện tại.

**Giới hạn:** cập nhật ghi đè xóa đi trạng thái trước đó; backup hoặc transaction log không phải API lịch sử có bảo đảm nghiệp vụ. Phương án này chỉ đủ khi mất lịch sử là quyết định được chấp nhận và đã có căn cứ rõ ràng.

### 2.2. Chỉ lưu lịch sử làm nguồn sự thật

Ví dụ lưu các lần chuyển trạng thái đơn hàng bằng bản ghi bất biến:

~~~sql
CREATE TABLE order_status_event (
    order_id       bigint NOT NULL,
    event_version  bigint NOT NULL CHECK (event_version >= 1),
    from_status    text,
    to_status      text NOT NULL,
    occurred_at    timestamptz NOT NULL,
    recorded_at    timestamptz NOT NULL DEFAULT now(),
    actor_id       bigint,
    reason         text,
    PRIMARY KEY (order_id, event_version)
);

CREATE INDEX ix_order_status_event_time
    ON order_status_event (order_id, occurred_at DESC, event_version DESC);
~~~

Một đơn có phiên bản 1 = NEW, 2 = PAID, 3 = PACKED, 4 = SHIPPED. Khi biết mọi lần chuyển đổi đều được ghi đúng thứ tự, trạng thái hiện tại có thể lấy từ phiên bản cao nhất:

~~~sql
SELECT to_status
FROM order_status_event
WHERE order_id = 42
ORDER BY event_version DESC
LIMIT 1;
~~~

**event_version** quyết định thứ tự áp dụng thay đổi cho từng đơn. **occurred_at** là thời gian nghiệp vụ xảy ra; **recorded_at** là thời điểm hệ thống ghi nhận, hai giá trị có thể khác nhau khi dữ liệu đến muộn. Không tự suy ra trạng thái hiện tại bằng cách sắp xếp **occurred_at** nếu sự kiện có thể đến trễ, có hiệu lực hồi tố hoặc cần điều chỉnh; quy tắc áp dụng phải được định nghĩa tường minh.

Lưu các thay đổi trạng thái như ví dụ phù hợp với việc dựng lại *trạng thái*, nhưng chưa phải event sourcing đầy đủ. Nếu dùng event sourcing, sự kiện nên mang ý nghĩa nghiệp vụ và có phiên bản schema (ví dụ **PaymentCaptured**, **ShipmentDispatched**); cần kiểm soát logic phát lại, khả năng xử lý sự kiện cũ và cách xây projection phục vụ đọc.

**Ưu điểm:** có dấu vết theo từng phiên bản, dễ phát hiện bước chuyển bất thường, phù hợp giải thích “đã xảy ra những gì”.

**Giới hạn:** đọc hiện tại hàng loạt cần chỉ mục, bản chiếu (*projection*) hoặc snapshot; dữ liệu tăng theo số thay đổi; việc sửa lỗi thường phải thêm bản ghi điều chỉnh và xác định lại thứ tự, không tùy tiện ghi đè quá khứ.

### 2.3. Lưu cả hiện tại và lịch sử

Một thực thể có thể phục vụ đồng thời hai mục tiêu:

~~~mermaid
flowchart LR
    A["Lệnh chuyển trạng thái"] --> B{"Kiểm tra chuyển đổi và phiên bản"}
    B -->|Hợp lệ| C["Một giao dịch dữ liệu"]
    C --> D[("orders: trạng thái mới nhất")]
    C --> E[("order_status_history: bản ghi thay đổi")]
    D --> F["API xem trạng thái hiện tại"]
    E --> G["Tra cứu quá khứ / kiểm toán"]
    B -->|Không hợp lệ| H["Từ chối hoặc thử lại"]
~~~

Ở dạng này, dữ liệu hiện tại và lịch sử phải được đồng bộ bằng cơ chế rõ ràng. Nếu cùng nằm trong một cơ sở dữ liệu quan hệ, một giao dịch thường là cách dễ kiểm chứng nhất; nếu nằm ở các dịch vụ khác nhau thì phải xác định nguồn sự thật, cơ chế phát sự kiện bền vững, phát lại và mức độ trễ chấp nhận được.

**Ưu điểm:** truy vấn hiện tại ít tốn công, đồng thời đáp ứng nhu cầu theo dõi và kiểm toán.

**Giới hạn:** thêm chi phí ghi, lưu trữ và kiểm thử tính nhất quán; cần quy định xóa dữ liệu, nâng cấp schema và xử lý thất bại giữa các bước.

## 3. Đặt câu hỏi đúng trước khi chọn

Khi phỏng vấn nghiệp vụ, nên ghi yêu cầu dưới dạng **câu hỏi phải trả lời được**, **mức chính xác**, **khoảng thời gian lưu** và **tần suất truy vấn**.

| Câu hỏi khám phá | Hệ quả lên mô hình |
|---|---|
| Người dùng chỉ xem giá trị đang có hay thường hỏi “tại ngày X”? | Chỉ hiện tại hoặc phải có phiên bản có mốc thời gian |
| Có tranh chấp, hoàn tiền, kiểm toán, pháp lý hoặc nhu cầu giải thích quyết định không? | Thường phải có lịch sử đáng tin cậy, người thay đổi và lý do |
| Giá trị quá khứ được phép chỉnh sửa hồi tố không? | Phải phân biệt thời gian hiệu lực với thời gian ghi nhận; cân nhắc bitemporal |
| Một thực thể đổi trạng thái vài lần hay hàng nghìn lần/ngày? | Tác động đến dung lượng, phân vùng, chỉ mục, chiến lược snapshot |
| Truy vấn hiện tại có yêu cầu độ trễ thấp ở quy mô lớn không? | Nên có bản hiện tại/projection được duy trì tốt |
| Ai có quyền xem hoặc xóa lịch sử? Lưu bao lâu? | Cần chính sách retention, che thông tin, bảo vệ dữ liệu cá nhân |
| Nếu sự kiện đến trễ, lặp, sai thứ tự hoặc xử lý lại thì sao? | Cần khóa idempotency, version, quy tắc thứ tự và cơ chế sửa sai |
| Đội vận hành có đủ khả năng duy trì replay, migration, giám sát độ lệch không? | Chi phí vận hành có thể khiến mô hình đơn giản hơn phù hợp hơn |

Có thể dùng luồng quyết định sau:

~~~mermaid
flowchart TD
    A["Nghiệp vụ cần trả lời câu hỏi về quá khứ?"] -->|Không| B["Lưu trạng thái hiện tại"]
    A -->|Có| C{"Có cần đọc trạng thái mới nhất nhanh, thường xuyên?"}
    C -->|Có| D["Lưu hiện tại + lịch sử"]
    C -->|Không| E["Lưu lịch sử làm nguồn sự thật"]
    D --> F{"Có thay đổi hồi tố hoặc cần biết hệ thống đã biết gì khi đó?"}
    E --> F
    F -->|Có| G["Thiết kế valid time + system time"]
    F -->|Không| H["Lịch sử một trục thời gian có thể đủ"]
~~~

Đây là khung khởi đầu, không phải thuật toán tuyệt đối. Ví dụ sổ cái có thể vừa lưu bút toán bất biến vừa xây projection số dư để đọc nhanh; khi đó phương án vật lý là “cả hai” nhưng **nguồn sự thật nghiệp vụ** vẫn là bút toán.

## 4. Thời gian nào được ghi lại?

Một bảng “history” thiếu định nghĩa thời gian dễ trả lời sai dù truy vấn SQL chạy đúng.

- **Thời gian hiệu lực (*valid time*)**: giá trị đúng trong thế giới nghiệp vụ vào khi nào. Ví dụ giá thuê bao có hiệu lực từ 01/05.
- **Thời gian ghi nhận (*system/transaction time*)**: hệ thống biết hoặc lưu phiên bản ấy từ lúc nào. Ví dụ đến 03/05 mới nhận được quyết định áp dụng giá từ 01/05.
- **Thời gian sự kiện (*event/occurred time*)**: hành động thực tế xảy ra lúc nào; có thể dùng làm valid time tùy ngữ nghĩa.
- **Thời gian xử lý (*processing time*)**: pipeline đọc hoặc tính toán sự kiện lúc nào; không mặc nhiên là thời gian hiệu lực.

Ví dụ bộ phận hỗ trợ vào ngày 05/05 điều chỉnh ngày bắt đầu gói dịch vụ từ 03/05 thành 01/05. Khi hỏi **“gói nào có hiệu lực ngày 02/05 theo hiểu biết hiện nay?”**, câu trả lời có thể là gói mới. Khi hỏi **“vào ngày 02/05 hệ thống đã biết điều gì?”**, câu trả lời vẫn có thể là gói cũ. Muốn trả lời cả hai, lưu một dấu thời gian **updated_at** là không đủ.

### 4.1. Lịch sử theo khoảng hiệu lực

Mô hình phiên bản thường dùng khoảng thời gian nửa mở **[valid_from, valid_to)**:

~~~text
Gói A: [2026-05-01 00:00, 2026-05-10 00:00)
Gói B: [2026-05-10 00:00, vô hạn)
~~~

Thời điểm đúng bằng 10/05 00:00 thuộc gói B, không đồng thời thuộc A. Dùng khoảng nửa mở giúp tránh trùng tại biên. Cần thống nhất múi giờ (thường lưu thời điểm theo UTC bằng **timestamptz**, hiển thị theo múi giờ nghiệp vụ), cách hiểu ngày không có giờ và thời điểm kết thúc vô hạn.

Một truy vấn “giá trị có hiệu lực tại T” theo khoảng:

~~~sql
SELECT plan_code
FROM customer_plan_version
WHERE customer_id = 100
  AND valid_from <= TIMESTAMPTZ '2026-05-09 15:00:00+00'
  AND (
      valid_to IS NULL
      OR TIMESTAMPTZ '2026-05-09 15:00:00+00' < valid_to
  );
~~~

Bảng ví dụ phải có ràng buộc ngăn hai phiên bản **cùng thực thể, cùng loại hiệu lực** chồng khoảng (trừ khi nghiệp vụ thực sự cho phép). Trong PostgreSQL có thể dùng **EXCLUDE** với kiểu range và chỉ mục GiST, hoặc kiểm tra chồng lấn được bảo vệ bằng giao dịch/khóa; chỉ tạo **UNIQUE(customer_id, valid_from)** là chưa đủ ngăn giao nhau giữa các khoảng.

### 4.2. Bitemporal khi cần biết cả “đúng khi nào” và “được biết khi nào”

Bản ghi hai chiều thời gian có thể mang các cột:

| Cột | Ý nghĩa |
|---|---|
| customer_id, plan_code | Thực thể và giá trị |
| valid_from, valid_to | Khoảng giá trị có hiệu lực theo nghiệp vụ |
| recorded_from, recorded_to | Khoảng phiên bản được hệ thống coi là đúng |
| correction_reason, source_id | Lý do sửa và căn cứ |

Truy vấn khái niệm với hai tham số **business_time** và **knowledge_time**:

~~~sql
SELECT plan_code
FROM customer_plan_bitemporal
WHERE customer_id = 100
  AND valid_from <= :business_time
  AND (valid_to IS NULL OR :business_time < valid_to)
  AND recorded_from <= :knowledge_time
  AND (recorded_to IS NULL OR :knowledge_time < recorded_to);
~~~

Các dấu **:business_time** và **:knowledge_time** là tham số do ứng dụng bind; không phải cú pháp biến trực tiếp trong trình chạy SQL PostgreSQL thông thường. Khi sửa một mốc quá khứ, phải giữ được phiên bản mà hệ thống đã từng tin là đúng, đóng khoảng ghi nhận cũ và tạo phiên bản được ghi nhận mới; có thể phải chia lại các khoảng hiệu lực. Cần định nghĩa hành vi khi một thay đổi hồi tố ảnh hưởng tới nhiều phiên bản.

**Bitemporal có chi phí đáng kể**: ràng buộc không chồng lấn theo từng lát thời gian, cập nhật hiệu lực hồi tố, truy vấn phức tạp và dung lượng lớn. Chỉ dùng khi hai câu hỏi thời gian thực sự là yêu cầu nghiệp vụ. Đối với tiến trình đơn hàng chỉ cần biết mỗi chuyển đổi được ghi nhận khi nào, lịch sử với một trục thời gian có thể đã đủ.

## 5. Thiết kế tham khảo: đơn hàng có trạng thái hiện tại và lịch sử

Giả sử hệ thống cần:

1. Hiển thị trạng thái đơn hàng nhanh.
2. Tra lại mọi lần đổi trạng thái, ai thực hiện, lý do.
3. Ngăn hai yêu cầu đồng thời làm mất thay đổi.
4. Đảm bảo bản trạng thái hiện tại và bản ghi lịch sử cùng thành công hoặc cùng thất bại.

Dưới đây là ví dụ PostgreSQL với trạng thái đã được đơn giản hóa để tập trung vào mô hình dữ liệu:

~~~sql
CREATE TABLE orders (
    order_id            bigint PRIMARY KEY,
    status              text NOT NULL
                        CHECK (status IN ('NEW', 'PAID', 'PACKED',
                                         'SHIPPED', 'CANCELLED')),
    status_version      bigint NOT NULL CHECK (status_version >= 1),
    status_changed_at   timestamptz NOT NULL
);

CREATE TABLE order_status_history (
    order_id       bigint NOT NULL REFERENCES orders(order_id),
    version        bigint NOT NULL CHECK (version >= 1),
    from_status    text,
    to_status      text NOT NULL
                   CHECK (to_status IN ('NEW', 'PAID', 'PACKED',
                                       'SHIPPED', 'CANCELLED')),
    changed_at     timestamptz NOT NULL,
    actor_id       bigint,
    reason         text,
    PRIMARY KEY (order_id, version),
    CHECK (from_status IS DISTINCT FROM to_status)
);

CREATE INDEX ix_order_history_as_of
    ON order_status_history (order_id, changed_at DESC, version DESC);
~~~

**Khóa chính (order_id, version)** định danh một thay đổi duy nhất của một đơn. **status_version** là phiên bản trạng thái hiện tại để kiểm soát ghi đồng thời. **changed_at** trong ví dụ này là thời gian hệ thống thực hiện chuyển đổi, không đại diện cho thời gian hiệu lực hồi tố. **actor_id** có thể trống khi chuyển đổi do hệ thống thực hiện; nếu cần kiểm toán, nên có thêm nguồn thực hiện như **actor_type** và correlation/request ID.

Khi tạo đơn hàng, ghi trạng thái ban đầu và bản lịch sử phiên bản 1 trong cùng transaction:

~~~sql
BEGIN;

INSERT INTO orders (order_id, status, status_version, status_changed_at)
VALUES (42, 'NEW', 1, statement_timestamp());

INSERT INTO order_status_history (
    order_id, version, from_status, to_status,
    changed_at, actor_id, reason
)
SELECT order_id, status_version, NULL, status,
       status_changed_at, NULL, 'Đơn được tạo'
FROM orders
WHERE order_id = 42;

COMMIT;
~~~

Khi một yêu cầu đổi từ **PACKED** sang **SHIPPED**, ứng dụng đã đọc phiên bản 4 và dùng một câu lệnh nguyên tử:

~~~sql
WITH transitioned AS (
    UPDATE orders
    SET status = 'SHIPPED',
        status_version = status_version + 1,
        status_changed_at = statement_timestamp()
    WHERE order_id = 42
      AND status = 'PACKED'
      AND status_version = 4
    RETURNING order_id, status_version, status_changed_at
)
INSERT INTO order_status_history (
    order_id, version, from_status, to_status,
    changed_at, actor_id, reason
)
SELECT order_id, status_version, 'PACKED', 'SHIPPED',
       status_changed_at, 1001, 'Bàn giao vận chuyển'
FROM transitioned
RETURNING order_id, version;
~~~

- Nếu điều kiện phiên bản/trạng thái không khớp, **transitioned** không có hàng; lịch sử không được chèn. Ứng dụng phải kiểm tra kết quả không có hàng, báo xung đột hoặc đọc lại rồi quyết định thử lại.
- Nếu chèn lịch sử vi phạm ràng buộc, **toàn bộ câu lệnh bị rollback**, gồm cả phần cập nhật trạng thái. Một câu lệnh SQL như trên là nguyên tử trong PostgreSQL.
- Điều kiện **status = 'PACKED'** mới bảo vệ ví dụ chuyển đổi cụ thể. Với nhiều quy tắc nghiệp vụ (như hủy đơn, hoàn tiền, xử lý giao nhận), cần xác thực đầy đủ trạng thái chuyển tiếp và quyền thực hiện trong service, hoặc ràng buộc tương ứng ở database.
- Ví dụ giả định tất cả đường ghi trạng thái đi qua giao thức này. Nếu một hệ khác cập nhật trực tiếp **orders**, tính đầy đủ của history không còn được bảo đảm. Có thể giới hạn quyền ghi, dùng stored procedure hoặc trigger nếu cần thực thi tập trung.

Tra cứu hiện tại:

~~~sql
SELECT status, status_version, status_changed_at
FROM orders
WHERE order_id = 42;
~~~

Tra cứu chuỗi lịch sử:

~~~sql
SELECT version, from_status, to_status, changed_at, actor_id, reason
FROM order_status_history
WHERE order_id = 42
ORDER BY version ASC;
~~~

Tra cứu trạng thái **đã được hệ thống ghi nhận** không muộn hơn thời điểm T:

~~~sql
SELECT to_status
FROM order_status_history
WHERE order_id = 42
  AND changed_at <= TIMESTAMPTZ '2026-05-10 10:10:00+00'
ORDER BY changed_at DESC, version DESC
LIMIT 1;
~~~

Nếu truy vấn không có hàng, có thể đơn chưa tồn tại ở T hoặc lịch sử không được lưu đủ xa; không tự diễn giải thành trạng thái **NEW**. Nếu cần truy vấn theo thời điểm phát sinh thực tế hay có hiệu lực hồi tố, phải mô hình hóa thêm **occurred_at/valid_from** theo ngữ nghĩa ở phần 4, thay vì giả định **changed_at** luôn đại diện cho mọi trục thời gian.

Thiết kế này cũng không tự bảo đảm history luôn chứa bản ghi cuối cho mọi hàng: khóa ngoại chỉ bảo vệ quan hệ từ lịch sử sang **orders**. Phải kiểm soát mọi đường ghi và có cơ chế đối soát định kỳ, chẳng hạn kiểm tra **orders.status_version = MAX(history.version)** và giá trị trạng thái cuối tương ứng.

## 6. Giữ lịch sử thế nào để không biến thành dữ liệu khó tin cậy?

### 6.1. Bất biến nghiệp vụ và sửa sai có dấu vết

Bản ghi lịch sử được coi là chứng cứ của thay đổi đã được ghi nhận thì nên **append-only** ở cấp nghiệp vụ: không xóa hoặc sửa một bước cũ chỉ để hệ thống “đẹp số liệu”. Nếu trạng thái **SHIPPED** được nhập nhầm, tạo chuyển đổi **đính chính** có lý do và người phê duyệt theo quy tắc nghiệp vụ. Trong bitemporal, việc đóng **recorded_to** của phiên bản cũ là thao tác quản lý hệ thống lịch sử đã được định nghĩa; nó không được xóa đi thông tin rằng hệ thống từng ghi nhận phiên bản đó.

Tuy nhiên, “append-only” không đồng nghĩa giữ dữ liệu cá nhân vĩnh viễn. Chính sách bảo mật và thời hạn lưu có thể yêu cầu xóa, ẩn danh hoặc mã hóa tách biệt dữ liệu nhạy cảm. Hãy thiết kế trường nhận dạng và payload theo mức tối thiểu cần thiết, thay vì sao chép toàn bộ PII vào mỗi bản ghi lịch sử.

### 6.2. Đồng thời, sự kiện đến lặp và sai thứ tự

Một số lỗi phổ biến:

- Hai người đổi cùng đơn ở phiên bản 4: nếu không kiểm tra phiên bản, lần ghi cuối có thể ghi đè sự thay đổi trước đó. Dùng optimistic locking hoặc khóa hàng/transaction phù hợp.
- Khách hàng bấm lại “Thanh toán”: nếu mỗi request tạo một event mới, lịch sử có thể chứa hai nghiệp vụ giống nhau. Dùng **idempotency key** duy nhất cho yêu cầu nghiệp vụ; retry phải trả kết quả phù hợp mà không nhân đôi thay đổi.
- Sự kiện từ hệ thống ngoài đến muộn: **recorded_at** có thể muộn hơn **occurred_at**. Cần quy tắc rõ việc nhận, bỏ qua, bù trừ hay hiệu chỉnh các trạng thái phát sinh sau đó.
- Đồng hồ nhiều máy lệch nhau: không lấy **timestamp** làm thứ tự duy nhất cho sự kiện đồng thời. Phiên bản tuần tự theo thực thể hoặc sequence nghiệp vụ mới là cơ sở đáng tin cho thứ tự áp dụng.

Khi cập nhật database và phát thông báo sang message broker, ghi database thành công nhưng gửi message thất bại sẽ tạo trạng thái lệch giữa dịch vụ. **Transactional outbox** (lưu thông báo cần phát trong cùng transaction với cập nhật dữ liệu, sau đó phát có retry) thường giải quyết khoảng trống này. Consumer vẫn cần idempotency; phát sự kiện *at-least-once* có thể dẫn đến giao nhận trùng.

### 6.3. Không nhầm audit, CDC, snapshot và lịch sử nghiệp vụ

| Cơ chế | Giải quyết tốt | Không tự bảo đảm |
|---|---|---|
| **Audit log** | Ai thao tác, hành động nào, từ nguồn nào | Giá trị hiệu lực tại mọi thời điểm hoặc logic nghiệp vụ chính xác |
| **CDC / database log** | Chuyển dữ liệu thay đổi sang hệ thống khác | Lưu lịch sử vô hạn, ngữ nghĩa nghiệp vụ, thứ tự liên dịch vụ |
| **Snapshot** | Đọc nhanh hoặc hỗ trợ tái dựng từ mốc gần đây | Mọi thay đổi giữa các snapshot |
| **Temporal version table** | Giá trị của thực thể tại những khoảng thời gian được định nghĩa | Vì sao thay đổi nếu không lưu reason/source |
| **Event sourcing** | Lưu sự kiện miền làm nguồn sự thật, có thể replay | Dễ nâng cấp sự kiện cũ, đơn giản khi vận hành hoặc truy vấn tùy ý |

Có thể phối hợp chúng, nhưng phải đặt tên đúng trách nhiệm. Ví dụ CDC được dùng chuyển **order_status_history** sang kho phân tích; bảng lịch sử vẫn là nơi định nghĩa ngữ nghĩa trạng thái, còn CDC là cơ chế truyền.

## 7. Khóa, ràng buộc, chỉ mục và dung lượng

Một mô hình lịch sử đúng về ý tưởng có thể chậm hoặc không bảo đảm toàn vẹn nếu thiếu quy tắc vật lý.

**Khóa và tính duy nhất.** Với lịch sử sự kiện, **(entity_id, version)** thường là khóa tự nhiên để bảo vệ thứ tự trong từng thực thể. Với phiên bản hiệu lực, có thể dùng khóa surrogate (**version_id**) và ràng buộc riêng trên **entity_id + khoảng hiệu lực**. Nếu lưu loại trạng thái khác nhau trong cùng bảng, ràng buộc phải tính đến **status_type**.

**Ràng buộc quan hệ.** Trạng thái phải thuộc tập hợp hợp lệ; một chuyển đổi không được nhảy qua bước cấm; phiên bản khởi tạo phải hiện diện; thời gian kết thúc phải lớn hơn thời gian bắt đầu; các khoảng hiệu lực không được chồng lấn ngoài chủ đích. Không phải mọi quy tắc đều biểu diễn được chỉ bằng CHECK: chuyển tiếp phụ thuộc hàng cũ hoặc nhiều bản ghi thường cần giao dịch/trigger/service.

**Chỉ mục theo truy vấn thật.** Đọc hiện tại dùng khóa **order_id**. Đọc lịch sử từng thực thể dùng **(order_id, version)** hoặc **(order_id, changed_at DESC, version DESC)**. Báo cáo mọi thay đổi trong một ngày trên hàng triệu đơn có thể cần chỉ mục theo thời gian độc lập, phân vùng theo tháng hoặc kho phân tích; chỉ mục theo **order_id** không tự tối ưu truy vấn quét theo ngày. Càng nhiều chỉ mục càng tăng chi phí INSERT/UPDATE và dung lượng.

**Lưu trữ và vòng đời.** Ước lượng dung lượng theo:

~~~text
số thực thể × thay đổi trung bình / thực thể / kỳ
             × kích thước một phiên bản
             × số kỳ lưu giữ
+ dung lượng chỉ mục, bản sao và sao lưu
~~~

Nếu giá của một triệu sản phẩm thay đổi mỗi giờ, lưu toàn bộ tài liệu sản phẩm sau mỗi thay đổi có thể rất tốn kém. Khi đó cân nhắc chỉ lưu cột thay đổi, lưu phiên bản cho thuộc tính cần truy vấn, hoặc gom theo khoảng hiệu lực. Tuy nhiên chỉ lưu *delta* làm việc tái dựng khó hơn và dễ hỏng nếu thiếu một bước; cần chứng minh lợi ích trước khi tối ưu.

**Xóa và retention.** Xác định thời gian lưu riêng cho dữ liệu vận hành, lịch sử kiểm toán và dữ liệu phân tích; có thể cần tách payload nhạy cảm khỏi định danh lịch sử. Không bật xóa cascade khiến bằng chứng lịch sử biến mất một cách tình cờ; với khóa ngoại như ví dụ, quy trình xóa đơn phải được thiết kế cùng chính sách lưu/xóa lịch sử.

**Chiến lược schema migration.** Khi thêm trạng thái mới hoặc đổi cấu trúc sự kiện, phải giữ khả năng đọc dữ liệu cũ. Event sourcing cần xử lý version của event, upcaster hoặc logic phát lại tương thích; bảng phiên bản có thể cần backfill với nguồn và mức tin cậy rõ ràng. Không gán một dấu thời gian giả cho dữ liệu lịch sử thiếu thông tin.

## 8. Phụ thuộc loại cơ sở dữ liệu và cách truy vấn

Cùng một yêu cầu thời gian có thể dẫn đến cấu trúc vật lý khác nhau:

| Kiểu dữ liệu / hệ thống | Cách thường dùng | Điểm cần cân nhắc |
|---|---|---|
| **Cơ sở dữ liệu quan hệ** | Bảng hiện tại, bảng version, event table; khóa ngoại, transaction, chỉ mục thời gian | Ràng buộc khoảng thời gian, ghi nguyên tử, thời gian lưu và phân vùng |
| **Document database** | Document hiện tại + collection history; đôi khi nhúng mảng thay đổi nhỏ | Document tăng vô hạn, giới hạn kích thước, transaction giữa tài liệu, truy vấn lịch sử |
| **Graph database** | Node/edge hiện tại hoặc phiên bản edge với valid_from/valid_to | Cạnh quan hệ thay đổi theo thời điểm, truy vấn đường đi tại T, tính nhất quán giữa các node |
| **Kho phân tích** | Bảng dimension kiểu SCD Type 2 và fact lưu khóa phiên bản theo thời gian | Thời gian tải dữ liệu, late-arriving dimension, ảnh hưởng tới join theo kỳ |
| **Event stream / event store** | Sự kiện bất biến, projection hiện tại, snapshot theo mốc | Replay, xử lý lỗi, tương thích schema, thứ tự và tính idempotent |

**SCD Type 1** ghi đè thuộc tính (gần với chỉ hiện tại); **SCD Type 2** giữ các phiên bản giá trị qua khoảng hiệu lực (gần với lịch sử). Đây là kỹ thuật kho dữ liệu, không phải bằng chứng rằng mọi thay đổi của hệ thống giao dịch đã được ghi lại. Nếu tải dữ liệu theo lô mỗi đêm mà không nhận đủ thay đổi trong ngày, kho phân tích không thể tái tạo các trạng thái trung gian đã bị ghi đè.

Với graph, lịch sử của **mối quan hệ** cũng quan trọng: một nhân viên thuộc nhóm A từ tháng 1 đến tháng 3 rồi sang nhóm B; nếu chỉ phiên bản hóa node nhân viên mà không phiên bản hóa cạnh **MEMBER_OF**, truy vấn tổ chức tại tháng 2 sẽ sai. Với document database, một mảng **history** nhúng vào một document rất tiện khi thay đổi ít nhưng cần tách collection khi lịch sử tăng không giới hạn.

## 9. Ba tình huống chọn mô hình

### Tình huống A: cấu hình hiển thị tạm của người dùng

Yêu cầu: chỉ cần bố cục giao diện mới nhất; thay đổi cũ không có giá trị hỗ trợ hay kiểm toán. Độ trễ đọc quan trọng, cấu hình có thể đặt lại.

**Chọn:** trạng thái hiện tại. Có thể thêm **updated_at** để đồng bộ hoặc xử lý xung đột ghi; không cần bảng lịch sử chỉ vì có khả năng tạo nó. Nếu sau này xuất hiện yêu cầu khôi phục phiên bản trước, cần đánh giá thêm version history, số phiên bản giữ và quyền truy cập.

### Tình huống B: sổ cái giao dịch

Yêu cầu: chứng minh dòng tiền, đối soát mỗi biến động, không được âm thầm sửa bút toán cũ. Số dư phải có thể kiểm chứng từ các bút toán có thẩm quyền.

**Chọn:** bút toán/sự kiện bất biến làm nguồn sự thật; có thể xây bảng số dư hiện tại làm projection để truy vấn nhanh. Bút toán điều chỉnh được ghi bổ sung với liên kết tới bút toán cần sửa; bản số dư không được phép thay thế chứng cứ giao dịch.

**Lưu ý:** mô hình sổ cái cần thêm các bất biến đặc thù như cân bằng tổng phát sinh Nợ/Có, tiền tệ, thứ tự hạch toán và quy tắc đóng kỳ; không thể suy ra đủ từ một bảng trạng thái chung.

### Tình huống C: trạng thái đơn hàng và hỗ trợ khách hàng

Yêu cầu: nhân viên xem trạng thái hiện tại hàng nghìn lần mỗi ngày, khách hàng cần timeline giao hàng, bộ phận hỗ trợ cần biết ai đổi trạng thái và vì sao.

**Chọn:** hiện tại + lịch sử, ghi nhất quán. Nếu đối tác vận chuyển gửi mốc “giao thành công” đến chậm, ghi riêng thời điểm vận chuyển thực tế và thời điểm hệ thống nhận; kiểm tra liệu cập nhật trễ có được phép đổi trạng thái mới nhất. Nếu có điều chỉnh hồi tố làm phát sinh tranh chấp, xác định xem cần lịch sử một trục hay bitemporal.

## 10. Kiểm chứng thiết kế trước khi triển khai

Kiểm thử dữ liệu phải kiểm tra **ý nghĩa câu trả lời**, không chỉ việc INSERT/SELECT chạy thành công:

| Kịch bản | Điều phải đúng |
|---|---|
| Tạo thực thể lần đầu | Có trạng thái ban đầu; nếu yêu cầu lịch sử đầy đủ thì có phiên bản khởi tạo |
| Chuyển trạng thái hợp lệ | Phiên bản tăng đúng một bước, trạng thái hiện tại bằng phiên bản lịch sử cuối |
| Hai yêu cầu cùng sửa một phiên bản | Chỉ một yêu cầu thành công, yêu cầu còn lại biết có xung đột |
| Thao tác bị lỗi khi ghi lịch sử | Không để trạng thái hiện tại đổi mà lịch sử thiếu |
| Request được gửi lại | Không nhân đôi cùng một thay đổi nghiệp vụ |
| Xem trạng thái tại T, trước khi tạo và đúng biên khoảng | Trả kết quả đúng; phân biệt “chưa tồn tại” với “không còn dữ liệu” |
| Dữ liệu đến muộn hoặc được sửa hồi tố | Phân biệt thời điểm hiệu lực với thời điểm hệ thống ghi nhận |
| Xóa/anonymize theo retention | Tuân thủ thời hạn lưu mà vẫn bảo vệ các bằng chứng bắt buộc |
| Nâng cấp schema | Dữ liệu/phiên bản cũ vẫn đọc hoặc phát lại được theo quy tắc đã định |

Một cách đối soát với mô hình **orders + order_status_history** là lấy bản lịch sử có **version** lớn nhất của từng đơn và so sánh với **orders.status_version** cùng **orders.status**. Nếu chênh lệch, cần cảnh báo và sửa theo quy trình có lưu dấu vết; không tự sửa hàng loạt khi chưa hiểu nguyên nhân.

## 11. Bài thực hành: biến yêu cầu mơ hồ thành quyết định rõ ràng

Một hệ thống quản lý gói dịch vụ nêu yêu cầu: “Cần xem gói khách đang dùng và kiểm tra khiếu nại về gói tính phí tháng trước.”

Hãy làm rõ bốn nhóm thông tin:

1. **Truy vấn:** cần xem gói **hiện tại**, gói **có hiệu lực vào ngày thanh toán**, hay gói mà **hệ thống đã tin là đúng lúc xuất hóa đơn**? Ba câu trả lời có thể khác nhau.
2. **Thay đổi:** chuyển gói có hiệu lực ngay hay đầu kỳ tiếp theo? Có cho phép sửa ngày hiệu lực lùi về quá khứ không? Khi sửa, hóa đơn đã chốt được điều chỉnh bằng nghiệp vụ nào?
3. **Bất biến:** một khách tại một thời điểm có được có nhiều gói cùng loại? Phiên bản nào được phép chồng khoảng? Những ai được chỉnh sửa, và phải ghi lý do nào?
4. **Vận hành:** lượng thay đổi, thời hạn lưu, chỉ mục theo khách/ngày, cách đồng bộ hệ thống thanh toán và cách xác minh không bị thiếu bản lịch sử?

Giả sử sản phẩm yêu cầu truy vấn hiện tại nhanh, lưu lịch sử 24 tháng, cho phép chỉnh ngày hiệu lực của gói sau khi khiếu nại và cần biết dữ liệu đã được hệ thống ghi nhận tại thời điểm xuất hóa đơn. Khi đó **bảng hiện tại + lịch sử bitemporal** là một ứng viên phù hợp. Nên đưa ví dụ “đăng ký gói A ngày 01/05, chuyển B hiệu lực 10/05, ngày 12/05 sửa B thành hiệu lực 08/05” vào kiểm thử và xác minh cả hai câu hỏi: gói hiệu lực ngày 09/05 theo thông tin mới nhất, và thông tin hệ thống đã biết vào 09/05.

Nếu bỏ yêu cầu hồi tố và chỉ cần timeline chuyển gói tại thời điểm thao tác, mô hình **hiện tại + lịch sử phiên bản một trục thời gian** sẽ đơn giản hơn đáng kể.

## 12. Nguyên tắc kết luận

Chọn mô hình theo **câu hỏi mà hệ thống bắt buộc trả lời** và **những thay đổi mà hệ thống phải chứng minh**:

- Chỉ cần giá trị mới nhất, chấp nhận ghi đè: **lưu hiện tại**.
- Lịch sử là nguồn sự thật, cần tái dựng diễn biến: **lưu lịch sử**, dựng projection/snapshot khi cần tốc độ.
- Vừa đọc hiện tại nhiều vừa phải giải thích quá khứ: **lưu cả hai** với giao thức nhất quán, khóa phiên bản và cơ chế đối soát.
- Có giá trị hồi tố hoặc cần biết “khi đó hệ thống biết gì”: bổ sung **hai trục thời gian** khi nghiệp vụ thực sự đòi hỏi.

Ở mỗi lựa chọn, hoàn thiện mô hình bằng khóa, ràng buộc, chỉ mục, hành vi ghi đồng thời, thời hạn lưu, quyền truy cập và các truy vấn mẫu. Một lược đồ dữ liệu tốt phải cho ra câu trả lời đúng qua thời gian, đủ dễ kiểm chứng, và có thể tiến hóa khi quy tắc nghiệp vụ thay đổi.
