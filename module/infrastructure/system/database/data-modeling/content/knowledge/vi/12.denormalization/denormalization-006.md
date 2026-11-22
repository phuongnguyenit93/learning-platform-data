# Nguồn dữ liệu chuẩn, dữ liệu dẫn xuất và trách nhiệm đồng bộ

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Xác định **nguồn dữ liệu chuẩn (authoritative source)** cho từng sự thật nghiệp vụ, kể cả khi cùng một thực thể xuất hiện tại nhiều bảng hoặc nhiều dịch vụ.
- Phân biệt **dữ liệu nguồn**, **ảnh chụp lịch sử** và **dữ liệu dẫn xuất (derived data)** theo ngữ nghĩa, thời điểm có hiệu lực và quy tắc cập nhật.
- Mô tả **data lineage**: một giá trị dẫn xuất được tạo từ đâu, theo phép biến đổi nào và tại phiên bản dữ liệu nào.
- Thiết lập **hợp đồng đồng bộ** gồm bên sở hữu, sự kiện kích hoạt, mức nhất quán, độ trễ, xử lý lặp/sai thứ tự, đối soát và cách tái dựng.
- Thiết kế một luồng PostgreSQL dùng **transactional outbox**, phiên bản tăng đơn điệu và **upsert có điều kiện** để bảo vệ bản sao phục vụ đọc.
- Chẩn đoán khi nào dữ liệu không khớp là độ trễ dự kiến, khi nào là vi phạm hợp đồng, và ai phải xử lý.

Bài thuộc chương **Phi chuẩn hóa** của **DATABASE_DATA_MODELING**. Chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng đòi hỏi nhiều hơn việc chọn thực thể, quan hệ, khóa, chỉ mục và lược đồ vật lý. Khi dữ liệu được sao chép sang mô hình quan hệ, document, đồ thị hoặc phân tích, thiết kế phải nói rõ **đâu là sự thật, ai chịu trách nhiệm giữ đúng và hệ thống kiểm chứng điều đó bằng cách nào**.

## 1. Một sản phẩm, nhiều bản ghi: nơi nào được quyết định giá trị đúng?

Giả sử hệ thống bán hàng có các nơi lưu dữ liệu sau:

| Nơi lưu | Dữ liệu | Mục đích |
| --- | --- | --- |
| **catalog_products** | Tên và giá niêm yết hiện hành của sản phẩm | Quản lý danh mục |
| **product_cards** | Tên và giá hiển thị trong danh sách tìm kiếm | Đọc nhanh, tránh gọi nhiều dịch vụ |
| **order_items** | Tên và giá đã chốt khi xác nhận đơn | Chứng cứ lịch sử giao dịch |
| **daily_sales_summary** | Tổng số lượng/giá trị đã bán theo ngày | Báo cáo và dashboard |

Bốn nơi có thể cùng lưu chuỗi tên sản phẩm hoặc một số tiền. Nhưng chúng **không cùng trả lời một câu hỏi**:

- **catalog_products.current_price** trả lời: giá niêm yết hiện tại là bao nhiêu?
- **product_cards.current_price_display** trả lời: giá hiển thị đã được đồng bộ đến phiên bản nào?
- **order_items.unit_price_at_confirmation** trả lời: giá được chấp nhận khi chốt dòng đơn là bao nhiêu?
- **daily_sales_summary.sales_amount** trả lời: tổng giá trị theo **định nghĩa báo cáo** và **kỳ dữ liệu** đã thống nhất là bao nhiêu?

Khi giá niêm yết thay đổi từ 150.000 thành 180.000 VND, bản sao **product_cards** cần được làm mới; **order_items** của đơn đã xác nhận phải giữ giá cũ; **daily_sales_summary** thường không được viết lại bằng giá niêm yết mới. Nếu tất cả đều được “đồng bộ cho giống nhau”, kết quả sẽ sai nghiệp vụ.

> **Nguồn chuẩn luôn gắn với một sự thật có ngữ nghĩa và thời điểm xác định.** Không có một bảng duy nhất mặc nhiên là nguồn chuẩn cho mọi cách hiểu của “giá sản phẩm”.

## 2. Nguồn chuẩn là quyền quyết định, không chỉ là nơi chứa dữ liệu

**Authoritative source** là thành phần có quyền xác định giá trị đúng của một thuộc tính theo một hợp đồng nghiệp vụ. Thành phần ấy thường cũng sở hữu quy tắc ghi và ràng buộc liên quan.

Cần phân biệt ba khái niệm:

1. **Nguồn chuẩn:** nơi có thẩm quyền thay đổi một sự thật nghiệp vụ. Ví dụ, dịch vụ danh mục quản lý tên niêm yết; dịch vụ định giá có thể quản lý giá áp dụng cho từng phân khúc khách.
2. **Bản sao hoặc projection:** dữ liệu được tạo từ nguồn chuẩn để phục vụ một access pattern, một API, cache hoặc một hệ thống khác. Nó phải làm mới hoặc tái dựng được theo hợp đồng.
3. **Sự thật lịch sử độc lập:** giá hoặc địa chỉ được ghi khi xác nhận giao dịch. Sau khi chốt, bản ghi giao dịch chính là nguồn chuẩn cho điều đã được xác nhận, dù lúc đầu giá trị được lấy từ bảng hiện hành.

Một cơ sở dữ liệu có primary và replica không có nghĩa rằng primary là **nguồn chuẩn nghiệp vụ cho mọi thuộc tính**. Primary/replica mô tả cơ chế lưu trữ và sao chép ở tầng hạ tầng. Nguồn chuẩn nghiệp vụ mô tả **ai được phép định nghĩa và thay đổi sự thật**.

Cũng không nên hiểu “single source of truth” là bắt buộc toàn hệ thống chỉ có một database. Trong hệ nhiều dịch vụ, mỗi nhóm thuộc tính có thể do một dịch vụ sở hữu. Điều quan trọng là **không có hai thành phần cùng tùy tiện quyết định một giá trị theo cùng ngữ nghĩa**.

### 2.1. Lập bảng quyền sở hữu theo sự thật nghiệp vụ

Ví dụ:

| Sự thật nghiệp vụ | Nguồn chuẩn | Nơi dẫn xuất | Quy tắc khi nguồn thay đổi |
| --- | --- | --- | --- |
| Tên sản phẩm hiện hành | Danh mục sản phẩm | Search index, thẻ sản phẩm | Cập nhật tên theo phiên bản nguồn |
| Giá niêm yết hiện hành | Hệ thống giá/danh mục theo hợp đồng | Cache, danh sách sản phẩm | Làm mới hoặc hết hạn theo độ trễ cam kết |
| Giá thực tế đã xác nhận | Dòng đơn đã chốt hoặc chứng từ giao dịch | Hóa đơn, báo cáo đơn hàng | Giữ lịch sử; hiệu chỉnh bằng nghiệp vụ riêng |
| Quan hệ người dùng đang theo dõi | Tập quan hệ **follows** | **follower_count** | Tăng/giảm chính xác hoặc làm mới theo hợp đồng |
| Doanh số ghi nhận theo ngày | Giao dịch thanh toán/kế toán theo định nghĩa | Bảng tổng hợp, dashboard | Tính theo sự kiện, mốc thời gian, tiền tệ |
| Địa chỉ mặc định hiện tại | Sổ địa chỉ khách hàng | Gợi ý trên giao diện | Làm mới khi khách sửa/xóa |
| Địa chỉ đã xác nhận để giao đơn | Bản ghi/chỉ dẫn giao hàng đã duyệt | Chứng từ và màn hình theo dõi | Giữ bản đã chốt; thay đổi qua revision |

Nếu chưa biết nơi nào có quyền quyết định một trường, **chưa thể thiết kế đồng bộ có kiểm soát**. Ví dụ, nếu hệ thống danh mục và hệ thống bán hàng đều được phép tự sửa **current_price** mà không có quy tắc phân xử, việc thêm hàng đợi sự kiện sẽ chỉ truyền đi xung đột nhanh hơn.

### 2.2. Nguồn chuẩn khác nguồn đọc thuận tiện

Một API có thể chủ yếu đọc từ **product_cards** vì hiệu năng. Điều đó không làm **product_cards** trở thành nguồn chuẩn cho giá niêm yết; nó vẫn là bản sao phục vụ đọc.

Ngược lại, nếu khách bấm “Đặt hàng” và giá sẽ được dùng để cam kết thanh toán, đường ghi phải xác thực giá theo nguồn được ủy quyền và quy tắc báo giá. Không thể suy rằng một cache vừa trả giá 180.000 VND là đủ chứng cứ giá đã được chốt.

## 3. Data lineage: mỗi kết quả dẫn xuất phải truy được đường nguồn

**Data lineage** là mô tả nguồn, phép biến đổi và hành trình của dữ liệu. Một bản sao hữu ích khi người vận hành trả lời được:

- Nó bắt nguồn từ **bảng, sự kiện, document hoặc dịch vụ nào**?
- Dùng **thuộc tính và định nghĩa nghiệp vụ nào**?
- Được tính theo **công thức, bộ lọc, grain, timezone và phiên bản quy tắc nào**?
- Nó thể hiện nguồn tại **phiên bản/mốc xử lý nào**?
- Có thể **tính lại từ nguồn** hay không?
- Nếu dữ liệu sai, **ai có quyền sửa nguồn và ai chịu trách nhiệm sửa projection**?

Ví dụ mô tả một số dữ liệu dẫn xuất:

| Trường dẫn xuất | Nguồn | Quy tắc | Dấu mốc cần lưu/quan sát |
| --- | --- | --- | --- |
| **product_cards.display_name** | **catalog_products.display_name** | Sao chép tên hiện hành | **source_version**, thời điểm projection nhận |
| **product_cards.current_price** | Giá hiện hành có thẩm quyền | Sao chép giá và currency, không suy từ giao dịch cũ | Phiên bản giá, đồng tiền |
| **orders.items_subtotal** | Các dòng hàng đã xác nhận | SUM(quantity × unit_price_at_confirmation) | Quy tắc tính, trạng thái dòng |
| **user_stats.follower_count** | Quan hệ **follows** đang tồn tại | COUNT các quan hệ hợp lệ | Mốc giao dịch hoặc checkpoint đồng bộ |
| **daily_sales_summary** | Các sự kiện thanh toán hợp lệ | SUM/COUNT theo ngày và tiền tệ | Watermark, timezone, phiên bản công thức |

Một tổng tiền được tính theo ngày **không thể cộng trực tiếp các loại tiền khác nhau**. Một bộ đếm “người dùng duy nhất” không thể tạo bằng cách cộng tùy ý các **COUNT(DISTINCT)** của từng ngày. Vì vậy, lineage phải ghi cả **ngữ nghĩa và công thức**, không chỉ “từ bảng A sang bảng B”.

### 3.1. Phân biệt ba loại mốc

- **Source version:** số phiên bản của thực thể nguồn, tăng mỗi lần dữ liệu liên quan thay đổi. Có thể dùng để bỏ qua sự kiện cũ.
- **Event/checkpoint hoặc watermark:** mốc đến đó consumer đã xử lý dữ liệu, thường dùng trong luồng hoặc dữ liệu phân tích. Không phải mọi sự kiện đều có cùng một thứ tự toàn cục.
- **Business effective time:** khi giá, trạng thái hay điều khoản có hiệu lực theo nghiệp vụ. Nó có thể khác thời điểm hệ thống ghi hoặc consumer nhận sự kiện.

Ba khái niệm này không thay thế nhau. Một sự kiện có thể được hệ thống nhận lúc 00:05 nhưng có hiệu lực cho giao dịch lúc 23:58 hôm trước. Một projection đã nhận event version 12 của sản phẩm A chưa có nghĩa đã cập nhật version 12 của mọi sản phẩm khác.

## 4. Hợp đồng đồng bộ phải diễn đạt thành điều kiểm chứng được

Nếu quyết định phi chuẩn hóa, cần coi nguồn và dữ liệu dẫn xuất là hai phần của **một hợp đồng dữ liệu**.

Ví dụ cho **product_cards**:

| Thành phần hợp đồng | Nội dung minh họa |
| --- | --- |
| Dữ liệu | Tên, giá niêm yết, currency, trạng thái hiển thị hiện hành của sản phẩm |
| Nguồn chuẩn | **catalog_products** do nhóm Catalog quản lý |
| Bản sao | **product_cards** do nhóm Search/Storefront quản lý |
| Định danh | **product_id** |
| Phiên bản | **source_version** tăng đơn điệu theo product_id |
| Cơ chế phát | Thay đổi nguồn + ghi outbox cùng giao dịch |
| Cơ chế nhận | Consumer upsert khi version mới hơn, có xử lý sự kiện lặp |
| Mức nhất quán | Eventual consistency cho trang danh sách |
| Giới hạn độ trễ | Ví dụ tối đa 30 giây trong điều kiện vận hành đã cam kết |
| Khi người dùng cần giá mới ngay | Đọc/đối chiếu nguồn giá khi xác nhận giao dịch |
| Xóa sản phẩm | Phát tombstone/version xóa và ẩn khỏi projection |
| Đối soát | So ID, phiên bản, trường giá/tên/trạng thái, phân loại lỗi |
| Phục hồi | Replay outbox/CDC hoặc rebuild theo snapshot + mốc sự kiện |
| Quan sát | Lag, backlog, retry, mismatch, số bản ghi thiếu/thừa |
| Chịu trách nhiệm | Nhóm Catalog cho giá trị nguồn và sự kiện; nhóm Search cho projection/consumer |

Các mốc thời gian và người sở hữu ở bảng là **ví dụ hợp đồng**, cần thay bằng quy định thực của tổ chức. Không được hứa “luôn đúng” nếu consumer thực chất cập nhật sau vài giây. Cũng không thể gọi một luồng là “gần thời gian thực” mà không định nghĩa cách đo độ trễ.

### 4.1. Cơ chế và cam kết đọc là hai vấn đề khác nhau

**Đồng bộ trong cùng transaction** có thể cung cấp cập nhật nguyên tử khi nguồn và bản sao cùng một database và mọi đường ghi tuân thủ giao thức. Tuy vậy, nó làm tăng ghi, khóa, độ phức tạp và có thể tạo điểm nóng.

**Đồng bộ bất đồng bộ** qua sự kiện giúp tách đường ghi khỏi mô hình đọc, nhưng bản sao có thể cũ. Cần xử lý sự kiện trùng, sai thứ tự, thất lạc, gián đoạn và backfill.

**Cache với TTL/invalidation** cũng là bản sao. TTL giới hạn một số tình huống giữ cache, nhưng không tự bảo đảm dữ liệu luôn mới trong mọi trường hợp; cache có thể được làm ấm sai hoặc vô hiệu hóa thất bại.

**Đọc từ read replica** có thể có replication lag. Đó là tính nhất quán của hạ tầng sao chép, vẫn cần được tính vào hành vi người dùng, nhưng không thay thế quyền sở hữu nguồn chuẩn nghiệp vụ.

## 5. Ví dụ PostgreSQL: một nguồn dữ liệu, một projection có phiên bản

Xét mô hình tối giản sau. **catalog_products** là nguồn chuẩn cho tên và giá niêm yết. **product_cards** là bảng dẫn xuất để API danh sách đọc nhanh; consumer cập nhật nó bất đồng bộ.

### 5.1. Lược đồ nguồn và outbox

~~~sql
CREATE TABLE catalog_products (
    product_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    current_price NUMERIC(14, 2) NOT NULL
        CHECK (current_price >= 0),
    currency CHAR(3) NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    source_version BIGINT NOT NULL DEFAULT 1
        CHECK (source_version >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE product_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id BIGINT NOT NULL,
    aggregate_version BIGINT NOT NULL CHECK (aggregate_version >= 1),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    UNIQUE (aggregate_type, aggregate_id, aggregate_version)
);
~~~

Giả định **mỗi phiên bản nguồn phát tối đa một sự kiện trạng thái đầy đủ cho projection**. Nếu một hệ thống cần nhiều sự kiện cho cùng phiên bản, ràng buộc UNIQUE và cách đánh phiên bản phải được thiết kế khác.

**product_outbox** là bảng trung gian để liên kết ghi nghiệp vụ với phát sự kiện. Nó **không phải** là một nền tảng giao vận message tự thân. Publisher phải đọc các hàng chưa phát, gửi có kiểm soát, đánh dấu trạng thái và thử lại khi lỗi. Trường **published_at** chỉ minh họa trạng thái phát; trong hệ thống thật còn cần kế hoạch xử lý cạnh tranh worker, retry/backoff và lưu log lỗi.

### 5.2. Ghi nguồn và sự kiện trong cùng transaction

Khi đổi tên và giá, sử dụng một giao dịch để bảo đảm sự kiện không tách khỏi thay đổi nguồn:

~~~sql
BEGIN;

WITH changed AS (
    UPDATE catalog_products
    SET display_name = $2,
        current_price = $3,
        currency = $4,
        source_version = source_version + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE product_id = $1
      AND is_deleted = FALSE
    RETURNING
        product_id,
        display_name,
        current_price,
        currency,
        is_deleted,
        source_version
)
INSERT INTO product_outbox (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    payload
)
SELECT
    $5::UUID,
    'Product',
    product_id,
    source_version,
    'ProductSnapshotChanged',
    jsonb_build_object(
        'productId', product_id,
        'displayName', display_name,
        'currentPrice', current_price,
        'currency', currency,
        'isDeleted', is_deleted,
        'sourceVersion', source_version
    )
FROM changed;

COMMIT;
~~~

Các tham số **$1 … $5** do ứng dụng truyền: ID sản phẩm, tên mới, giá mới, currency và một UUID sự kiện. Trước khi commit, ứng dụng phải kiểm tra đúng bản ghi được cập nhật; nếu **changed** rỗng vì sản phẩm không tồn tại/đã xóa thì không được báo đổi giá thành công.

Tính chất quan trọng: **UPDATE** và **INSERT outbox** cùng commit hoặc cùng rollback. Nếu một giao dịch ghi nguồn thất bại, nó không để lại sự kiện nói rằng giá đã đổi. Nếu commit thành công nhưng publisher đang dừng, sự kiện vẫn tồn tại để thử phát lại sau.

Cũng cần nói rõ giới hạn: **outbox không tự tạo giao hàng chính xác một lần**. Publisher có thể gửi được message nhưng chết trước khi đánh dấu **published_at**, khiến message được gửi lại. Consumer vẫn cần xử lý trùng.

**Phiên bản nguồn** được tăng dưới thao tác UPDATE trên hàng sản phẩm; hai giao dịch sửa cùng hàng sẽ chịu kiểm soát tương tranh của PostgreSQL. Điều này có ích cho thứ tự phiên bản **trong một product_id**, không tạo thứ tự toàn cục trên mọi sản phẩm.

Nếu cùng một **lệnh của người dùng** được thử lại, thao tác UPDATE có thể tăng version lần nữa. Hệ thống cần **idempotency key ở tầng command** khi một lần đổi giá không được thực hiện nhiều lần; idempotency ở consumer chỉ bảo vệ bản sao khỏi nhận lại **cùng một event**.

### 5.3. Lược đồ projection

~~~sql
CREATE TABLE product_cards (
    product_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    current_price NUMERIC(14, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    is_deleted BOOLEAN NOT NULL,
    source_version BIGINT NOT NULL CHECK (source_version >= 1),
    projected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Đây là lược đồ phục vụ đọc; **product_cards** không tự quyết định giá hiện hành. Ứng dụng đọc thẻ đang hiển thị có thể lọc:

~~~sql
SELECT
    product_id, display_name, current_price, currency
FROM product_cards
WHERE is_deleted = FALSE
ORDER BY product_id
LIMIT 50;
~~~

Nếu truy vấn thực cần sắp xếp theo thời gian tạo hoặc xếp hạng, projection và chỉ mục phải chứa thông tin theo **access pattern thực tế**; ví dụ trên chỉ thể hiện nguồn đọc.

### 5.4. Consumer chỉ áp dụng phiên bản mới hơn

Giả sử consumer đã xác thực event dạng snapshot đầy đủ và ánh xạ ra tham số. Một lần ghi vào PostgreSQL:

~~~sql
INSERT INTO product_cards (
    product_id,
    display_name,
    current_price,
    currency,
    is_deleted,
    source_version,
    projected_at
)
VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)
ON CONFLICT (product_id)
DO UPDATE SET
    display_name = EXCLUDED.display_name,
    current_price = EXCLUDED.current_price,
    currency = EXCLUDED.currency,
    is_deleted = EXCLUDED.is_deleted,
    source_version = EXCLUDED.source_version,
    projected_at = CURRENT_TIMESTAMP
WHERE product_cards.source_version < EXCLUDED.source_version;
~~~

Điều kiện **WHERE** có ba tác dụng:

1. Khi consumer nhận phiên bản **mới hơn**, bản sao được cập nhật.
2. Khi consumer nhận lại **cùng phiên bản**, giá trị đã áp dụng không bị thay đổi.
3. Khi sự kiện **cũ đến sau**, nó không ghi đè giá trị mới hơn.

Đây là mô hình **last version wins**, không phải tùy tiện “last arrival wins”. Nó chỉ an toàn khi **source_version tăng đơn điệu trong một product_id**, event chứa snapshot nhất quán của các trường, và không có hai trạng thái khác nhau cùng một version.

Ví dụ:

~~~text
Nguồn Product #501:
  v7 = Tên A, giá 150000
  v8 = Tên B, giá 180000
  v9 = Tên C, giá 175000

Thứ tự consumer nhận: v8 -> v9 -> v7 -> v9
Projection cuối:     v9
Sự kiện v7/v9 lặp:   bỏ qua, không làm cũ dữ liệu
~~~

**Lưu ý quan trọng về xóa:** nếu sản phẩm bị xóa khỏi nguồn, cần sự kiện **is_deleted = true** với version cao hơn và projection phải giữ **tombstone/version xóa** đủ lâu. Nếu xóa sạch hàng projection nhưng vẫn có sự kiện cũ đang chờ, event cũ có thể INSERT lại sản phẩm đã xóa. Trong mô hình ví dụ, nguồn dùng **soft delete** và consumer giữ hàng **is_deleted = true** để tránh phục hồi sai. Khi xóa vật lý hoặc giới hạn thời gian giữ tombstone, cần giao thức an toàn cho late events và rebuild.

### 5.5. Vì sao không cho giao diện sửa trực tiếp product_cards?

Nếu trang quản trị cho phép UPDATE **product_cards.current_price** mà không cập nhật nguồn:

- Trang danh sách có giá mới, chi tiết sản phẩm từ nguồn có giá cũ.
- Một event tiếp theo có thể ghi đè giá “vừa sửa”.
- Consumer không biết giá do ai quyết định, và đối soát có thể biến thành cuộc tranh luận chọn bên nào là đúng.

Vì vậy, đường ghi nghiệp vụ phải đi tới **catalog_products** (hoặc dịch vụ giá có thẩm quyền). Projection chỉ được cập nhật bởi pipeline đã chỉ định và công cụ phục hồi có kiểm soát. Phân quyền database và API phải phản ánh quyền sở hữu này.

## 6. Các hình thức đồng bộ và giới hạn của chúng

Không có cơ chế phù hợp cho mọi loại dữ liệu. Chọn theo **độ nhất quán nghiệp vụ yêu cầu**, **số đường ghi** và **phạm vi kho dữ liệu**.

| Cơ chế | Khi nào phù hợp | Trách nhiệm quan trọng |
| --- | --- | --- |
| **Cùng một giao dịch SQL** | Nguồn và tổng/bản sao ở cùng DB, cần khớp ngay | Mọi INSERT/UPDATE/DELETE cùng quy tắc, kiểm soát khóa và retry |
| **Trigger / stored procedure** | Muốn tập trung cập nhật khi nhiều tác nhân ghi cùng DB | Quản lý triển khai trigger, lỗi, deadlock, thời gian ghi và quyền sửa |
| **Outbox + message consumer** | Projection ở kho khác, cho phép trễ | Ghi outbox nguyên tử, phát lại, dedupe/version, backlog, rebuild |
| **CDC từ nhật ký thay đổi** | Cần truyền thay đổi từ DB sang hệ đọc/phân tích | Bảo toàn mốc snapshot, thứ tự, schema evolution, thao tác xóa |
| **Materialized view / refresh** | Tổng hợp nặng, có lịch làm mới | Độ tươi dữ liệu, thời gian refresh, nguồn và chiến lược tính lại |
| **Cache TTL/invalidation** | Đọc lặp dữ liệu ít đổi, có chính sách dữ liệu cũ | Invalidation, quyền truy cập, phân biệt cache miss và nguồn |
| **Tính lại khi đọc** | Truy vấn vẫn đạt SLO, dữ liệu cần chính xác theo nguồn | Chỉ mục, truy vấn, phân trang và tải nguồn |

Ví dụ, **số lượng tồn kho dùng để chốt bán** có thể cần một quy trình giữ chỗ/trừ tồn nhất quán tại nguồn. **Số tồn hiển thị mang tính tham khảo** có thể là projection được cập nhật theo sự kiện. Nếu dùng cùng một giá trị cache để cam kết bán, mô hình đã trao quyền quyết định cho nơi không có thẩm quyền.

### 6.1. “Ghi đồng bộ” không đồng nghĩa “mọi người đọc thấy ngay” trong hệ phân tán

Một thao tác cập nhật nguồn và outbox cùng transaction vẫn **chưa cập nhật product_cards** ở kho khác ngay khi commit. Tính nguyên tử chỉ bao trùm **nguồn + outbox**.

Nếu sau khi người quản trị đổi tên, giao diện phải đọc được tên mới ngay, có thể:

- Đọc trả từ **nguồn chuẩn** trong thao tác quản trị.
- Trả **source_version** rồi chờ projection đạt version ấy với timeout/hành vi dự phòng được định nghĩa.
- Tạm hiển thị kết quả vừa ghi và ghi rõ khi danh sách công khai vẫn đang đồng bộ.

Không được khẳng định consistency mạnh chỉ vì hệ thống dùng outbox. Cần xác định người đọc nào và thời điểm nào có quyền kỳ vọng dữ liệu mới.

## 7. Trách nhiệm đồng bộ cần phân công đến đúng nơi

Một bản sao thường đi qua ít nhất bốn vai trò: **nhóm nguồn**, **nhóm phát thay đổi**, **nhóm sở hữu projection**, và **nhóm vận hành/kiểm chứng**. Trong tổ chức nhỏ, một nhóm có thể kiêm nhiều vai trò; nhưng trách nhiệm vẫn phải được ghi rõ.

| Hoạt động | Bên chịu trách nhiệm chính | Điều cần bàn giao |
| --- | --- | --- |
| Định nghĩa tên/giá hiện hành | Chủ sở hữu nghiệp vụ và nguồn Catalog | Ngữ nghĩa, validation, quyền ghi, các trường có hiệu lực |
| Tăng version và ghi outbox | Bên triển khai đường ghi nguồn | Sự kiện từ mọi đường ghi, transaction nguyên tử |
| Định dạng và phiên bản sự kiện | Nhóm phát + nhóm tiêu thụ thống nhất | Schema, ý nghĩa field, version, chính sách tương thích |
| Áp dụng sự kiện và xây projection | Chủ sở hữu Search/Storefront | Dedupe, thứ tự, upsert, xóa/tombstone |
| Độ tươi và trải nghiệm đọc | Chủ sở hữu API đọc phối hợp nguồn | SLO, fallback khi trễ, nhãn “cập nhật đến…” nếu cần |
| Đối soát dữ liệu | Nguồn và projection cùng chịu trách nhiệm | Phép so, mốc dữ liệu, phân loại và quy trình xử lý sai |
| Backfill / rebuild | Chủ sở hữu projection, nguồn cung cấp mốc nhất quán | Snapshot, offset/watermark, đối soát trước chuyển đọc |
| Sự cố và cảnh báo | Nhóm vận hành với chủ sở hữu cụ thể | Lag, backlog, mismatch, runbook, người nhận cảnh báo |
| Xóa và thay đổi quyền truy cập | Chủ sở hữu dữ liệu + các consumer | Xóa/ẩn/thu hồi ở mọi bản sao theo chính sách |

**Không nên để tình huống “ai cũng dùng, không ai sở hữu”.** Nếu một nhóm tạo bảng tổng hợp cho báo cáo nhưng không ai có trách nhiệm khi công thức đổi, số liệu có thể sai hàng tháng dù pipeline vẫn chạy.

Một thỏa thuận đồng bộ nên chỉ ra **đầu mối khi gặp lỗi cụ thể**. Ví dụ: event thiếu trường bắt buộc do publisher là lỗi hợp đồng nguồn; consumer áp dụng version cũ là lỗi projection; định nghĩa “doanh thu” thay đổi thì nghiệp vụ và nhóm dữ liệu phải cập nhật công thức, schema và backfill.

## 8. Những lỗi đồng bộ thường gặp và cách nhận biết

| Dấu hiệu | Nguyên nhân có thể | Biện pháp |
| --- | --- | --- |
| Nguồn đã đổi nhưng không có event | Ghi nguồn bỏ qua outbox, gửi event sau commit thất bại | Cùng transaction, kiểm kê mọi đường ghi, đối soát outbox |
| Một thay đổi được áp dụng hai lần | Publisher/consumer retry, không idempotent | Event ID, version, dedupe hoặc upsert có điều kiện |
| Giá mới bị ghi đè bằng giá cũ | Event đến sai thứ tự | So version nguồn theo thực thể, không cập nhật vô điều kiện |
| Bản ghi bị xóa xuất hiện lại | Xóa vật lý projection, event cũ tới sau | Tombstone có version hoặc chiến lược chống hồi sinh |
| Một số sản phẩm cập nhật, một số không | Worker dừng giữa lô, lỗi phân trang, retry thiếu | Theo dõi tiến độ, idempotency, replay và đối soát |
| Projection cùng version nhưng khác giá | Mapping sai, bug biến đổi, sửa trực tiếp projection | Kiểm chứng payload, hạn chế quyền ghi, rebuild |
| Backfill ghi giá cũ lên event mới | Snapshot lịch sử đang chạy đồng thời pipeline | Upsert chỉ khi version mới hơn, mốc snapshot và catch-up |
| Chỉ số hôm nay sai vì event đến muộn | Nhóm theo lúc nhận thay vì lúc nghiệp vụ có hiệu lực | Định nghĩa business time, watermark, tính lại nhóm bị ảnh hưởng |
| API đọc cũ ngay sau khi ghi | Projection eventual consistency | Đọc từ nguồn, chờ version hoặc cơ chế hiển thị trạng thái |
| Một trường có hai nguồn tự sửa | Không rõ authority, xung đột giữa dịch vụ | Phân chia quyền sở hữu theo thuộc tính và hợp đồng quyết định |

Một sai lầm là xem **retry** như cách bảo đảm đúng đắn hoàn chỉnh. Retry có thể giải quyết lỗi tạm thời, nhưng nếu hành động **không idempotent**, retry chính là nguyên nhân nhân đôi bộ đếm hoặc ghi đè trạng thái.

### 8.1. Không tùy tiện dùng “last write wins” theo thời gian nhận

Giả sử hai dịch vụ đều phát sự kiện về địa chỉ hiện hành, một sự kiện đến muộn. Nếu consumer chọn message đến cuối, trạng thái cũ có thể thắng. Nếu chọn timestamp từ hai máy, chênh lệch đồng hồ và ngữ nghĩa timestamp cũng gây lỗi.

Cần làm rõ **ai có quyền ghi**, **thứ tự nghiệp vụ** (version/sequence được cấp ở nguồn), và **cách giải quyết xung đột** nếu thực sự có nhiều người ghi. Với các dữ liệu cần cộng tác đa chủ thể, chính sách hòa giải có thể phức tạp; không nên để sự kiện đến sau tự động thắng mà không có yêu cầu nghiệp vụ cho phép.

## 9. Đối soát: so cùng ý nghĩa, cùng thời điểm hoặc phiên bản

Với **catalog_products** và **product_cards** ở ví dụ PostgreSQL, một phép đối soát đọc từ cả nguồn và projection:

~~~sql
SELECT
    COALESCE(s.product_id, p.product_id) AS product_id,
    s.source_version AS source_version,
    p.source_version AS projection_version,
    CASE
        WHEN s.product_id IS NULL THEN 'ORPHAN_PROJECTION'
        WHEN p.product_id IS NULL THEN 'MISSING_PROJECTION'
        WHEN p.source_version > s.source_version THEN 'VERSION_AHEAD'
        WHEN p.source_version < s.source_version THEN 'LAGGING'
        WHEN p.display_name IS DISTINCT FROM s.display_name
          OR p.current_price IS DISTINCT FROM s.current_price
          OR p.currency IS DISTINCT FROM s.currency
          OR p.is_deleted IS DISTINCT FROM s.is_deleted
            THEN 'VALUE_MISMATCH'
        ELSE 'MATCH'
    END AS sync_state
FROM catalog_products AS s
FULL OUTER JOIN product_cards AS p
    ON p.product_id = s.product_id;
~~~

Ý nghĩa kết quả:

- **MATCH:** cùng version và cùng trường được kiểm tra ở snapshot truy vấn hiện tại.
- **LAGGING:** projection đang ở version thấp hơn nguồn; có thể bình thường trong cửa sổ đồng bộ.
- **VALUE_MISMATCH:** cùng version nhưng dữ liệu khác; đây thường là lỗi mapping, sửa trực tiếp hoặc phát sự kiện không nhất quán.
- **VERSION_AHEAD:** projection có version cao hơn nguồn được đọc; cần điều tra cách khôi phục nguồn, thay đổi quyền sở hữu hoặc version.
- **MISSING/ORPHAN:** có bản ghi chỉ ở một bên; cần đối chiếu với thời điểm tạo/xóa, chính sách retention và giai đoạn backfill.

Phép SQL trên là minh họa cho **hai bảng ở cùng PostgreSQL**. Khi nguồn và projection ở hai hệ thống khác nhau, không thể mặc định JOIN trực tiếp; cần xuất mẫu hoặc so kết quả ở cùng **watermark/phiên bản** bằng pipeline kiểm tra có kiểm soát.

**Không đếm mọi LAGGING là lỗi ngay lập tức.** Nếu hợp đồng cho phép trễ 30 giây, cần biết bản ghi nào đã chờ quá 30 giây tính từ mốc phù hợp; sự kiện vừa commit có thể chưa tới. Việc chỉ so version cho biết **còn thiếu bao nhiêu phiên bản**, chưa trực tiếp cho biết **đã trễ bao nhiêu giây**. Để đo thời gian, cần thêm metadata về commit/nhận/áp dụng sự kiện hoặc cơ chế checkpoint đáng tin.

**Cũng không dùng dữ liệu hiện hành để đối soát snapshot lịch sử.** Giá đã chốt trên đơn không phải bằng giá niêm yết hôm nay. Bất biến của đơn phải dựa vào chứng cứ xác nhận, công thức tính tiền và dữ liệu lịch sử phù hợp.

## 10. Độ tươi, chất lượng và khả năng phục hồi là chỉ số vận hành

Một hợp đồng đồng bộ có thể đặt các chỉ số:

| Chỉ số | Ý nghĩa | Ví dụ cảnh báo |
| --- | --- | --- |
| **End-to-end lag** | Từ khi thay đổi nguồn commit tới khi bản sao phục vụ đọc | Vượt ngưỡng SLO đã công bố |
| **Consumer backlog** | Số/thời gian của event đang chờ xử lý | Tăng liên tục hoặc không giảm sau sự cố |
| **Retry/dead-letter** | Sự kiện xử lý lỗi hoặc bị tạm cách ly | Vượt mức bình thường |
| **Mismatch count** | Số bản ghi vi phạm hợp đồng tại mốc được kiểm chứng | Cùng version nhưng sai giá/tên |
| **Missing projection** | Số bản ghi nguồn không có projection hợp lệ | Quá tuổi cho phép kể từ khi tạo nguồn |
| **Rebuild duration** | Thời gian tái tạo projection tới trạng thái bắt kịp | Vượt cửa sổ khôi phục đã đặt |
| **Read fallback rate** | Tỷ lệ API phải đọc nguồn vì projection chưa kịp | Tăng bất thường, ảnh hưởng tải nguồn |

Định nghĩa metric phải cho biết **cửa sổ thời gian, phân vị, phạm vi và cách lấy mẫu**. “Tối đa 30 giây” là cam kết mạnh hơn “p95 dưới 30 giây”; không được đánh đồng hai câu. Nếu sự kiện có thể mất, chỉ theo dõi lag của sự kiện **đã nhận** là chưa đủ: một hàng outbox chưa phát có thể không xuất hiện trong số liệu consumer. Cần giám sát cả phía nguồn và đường phát.

Khi hệ thống vượt ngưỡng, chủ sở hữu phải có **runbook**: xác định khâu dừng, ngăn dữ liệu sai tiếp tục được phục vụ nếu cần, xử lý/replay có kiểm soát, đối soát lại và quyết định khi nào mở đường đọc.

## 11. Backfill và rebuild không được ghi đè sự thật mới

Tạo projection lần đầu cho hàng triệu sản phẩm thường cần **backfill**. Một quy trình chỉ sao chép bảng nguồn rồi bật consumer có thể bỏ sót event xảy ra giữa hai bước.

Một cách tiếp cận có kiểm soát:

1. **Chọn mốc snapshot hoặc checkpoint** có thể gắn với luồng thay đổi; ghi lại mốc ấy.
2. **Bắt đầu thu thập thay đổi** từ trước/đúng mốc tương ứng, bảo đảm không có khoảng trống khi chuyển từ ảnh chụp sang luồng.
3. **Nạp snapshot nguồn** vào projection, có **source_version** của từng sản phẩm.
4. **Áp dụng phần thay đổi còn thiếu** với upsert chỉ nhận version cao hơn; replay event cũ không được làm lùi bản ghi.
5. **Đối soát theo mốc nhất quán**, kiểm tra bản ghi thiếu, dữ liệu khác version và tombstone.
6. **Chuyển đường đọc dần**, theo dõi hiệu năng và độ đúng; có phương án quay về đọc nguồn nếu phát hiện sai.

Ví dụ: backfill đọc sản phẩm version 7, nhưng consumer đã áp dụng event version 9. Nếu backfill dùng UPDATE vô điều kiện, projection bị lùi về version 7. Dùng **ON CONFLICT ... DO UPDATE ... WHERE product_cards.source_version < EXCLUDED.source_version** giúp ngăn ghi lùi, nhưng **không tự bảo đảm không bị bỏ sót sự kiện** nếu quá trình lấy snapshot và thu luồng không có checkpoint nối nhau.

Nếu phải tái dựng toàn bộ, nên tạo một projection mới, nạp và bắt kịp ở cùng mốc, đối soát rồi chuyển đọc. Việc xóa bảng đang phục vụ và xây lại ngay trên đó có thể gây gián đoạn và mất khả năng so sánh. Lựa chọn cụ thể phụ thuộc hệ thống, dung lượng và giới hạn triển khai.

### 11.1. Thay đổi schema và quy tắc biến đổi

Khi nguồn bổ sung **currency**, đổi cách tính giá hoặc thay tên trường, consumer cũ có thể đọc sai event mới. Cần có:

- **Phiên bản hợp đồng sự kiện**, định nghĩa field bắt buộc/tùy chọn và quy tắc tương thích.
- **Phiên bản phép biến đổi** nếu một số liệu dẫn xuất thay đổi công thức mà cùng version nguồn không đủ để phân biệt kết quả.
- **Triển khai có thứ tự** cho producer/consumer để cả phiên bản cũ và mới được xử lý trong giai đoạn chuyển tiếp.
- **Kế hoạch backfill/recompute** cho dữ liệu lịch sử nếu công thức mới áp dụng hồi tố.
- **Kiểm tra tương thích và đối soát** trước khi ngừng đường cũ.

Đừng nhầm **source_version** của một sản phẩm với **schema_version** của event. Một bên mô tả trạng thái của sản phẩm; bên kia mô tả cách diễn giải cấu trúc thông điệp. Đối với số liệu phân tích, đôi khi cần thêm **calculation_version** và kỳ dữ liệu.

## 12. Quyền ghi, quyền đọc, xóa dữ liệu và trách nhiệm với bản sao

Trách nhiệm đồng bộ còn liên quan đến bảo mật và thời hạn lưu giữ:

- **Chỉ chủ sở hữu nguồn** hoặc đường ghi được ủy quyền mới được thay đổi sự thật hiện hành; consumer không ghi ngược vào nguồn chỉ vì phát hiện mismatch.
- **Projection có thể cần quyền đọc hẹp hơn** dữ liệu nguồn. Không nên sao chép số điện thoại, địa chỉ, email hoặc dữ liệu nhạy cảm sang search index nếu UI không cần.
- **Xóa/ẩn dữ liệu** phải truyền đến mọi bản sao, cache, file export và mô hình phân tích trong phạm vi chính sách áp dụng.
- **Tombstone** dùng để chống phục hồi bản ghi cũ cần được thiết kế phù hợp với yêu cầu xóa dữ liệu; có thể giữ định danh/phiên bản tối thiểu thay vì giữ toàn bộ nội dung đã xóa.
- **Log sự kiện và dead-letter queue** cũng là nơi dữ liệu có thể tồn tại; chính sách lưu trữ, phân quyền và xóa phải tính tới chúng.
- **Bản chụp lịch sử** phục vụ chứng cứ giao dịch có thời hạn lưu và quyền truy cập riêng; không được xóa hoặc cập nhật theo quy tắc cache hiện hành một cách máy móc.

Một lỗi thường bị bỏ qua: khách đổi quyền hiển thị ảnh đại diện, profile chính đã ẩn ảnh nhưng read model vẫn công khai URL cũ. Khi đó projection không chỉ “hơi chậm” mà có thể vi phạm quy tắc truy cập. **Độ trễ có thể chấp nhận phụ thuộc loại dữ liệu và tác động nghiệp vụ**, không phải mọi field đều dùng chung ngưỡng 30 giây.

## 13. Chọn đúng chiến lược theo loại dữ liệu và mô hình lưu trữ

| Nhu cầu | Nguồn chuẩn gợi ý | Hình thức dữ liệu dẫn xuất | Điều phải kiểm chứng |
| --- | --- | --- | --- |
| Thẻ sản phẩm đọc nhiều | Danh mục/giá có thẩm quyền | Bảng card, cache, search document | Version, giá, tên, trạng thái, lag |
| Lịch sử đơn hàng | Giao dịch đã xác nhận | Có thể là bản snapshot nằm ngay trong đơn | Không đổi theo giá/địa chỉ hiện hành; có dấu vết hiệu chỉnh |
| Bộ đếm người theo dõi | Tập quan hệ follow còn tồn tại | Counter trong hồ sơ hoặc read model | INSERT/DELETE/retry, chống đếm trùng |
| Dashboard doanh số | Payment/sales events theo định nghĩa chỉ số | Aggregate table, materialized view, warehouse | Grain, tiền tệ, business time, watermark, late events |
| Tìm kiếm toàn văn | Nội dung được quản lý ở nguồn | Search index/document | Schema, cập nhật/xóa, quyền truy cập, rebuild |
| Truy vấn quan hệ đồ thị | Các đỉnh/cạnh có thẩm quyền | Thuộc tính dẫn xuất/bộ đếm trên đỉnh | Fan-out khi thêm/xóa cạnh, độ sâu và tính đúng của thống kê |

Trong **mô hình quan hệ**, ràng buộc khóa ngoại và transaction giúp duy trì một số bất biến cùng DB, nhưng không tự làm mới bản sao ở bảng khác nếu không thiết kế cập nhật.

Trong **document database**, nhúng thông tin tác giả vào mỗi bài có thể tăng tốc đọc nhưng làm đổi tên tác giả phát sinh **fan-out cập nhật**. Nguồn chuẩn có thể là document tài khoản; bản nhúng là projection nếu nó phải luôn phản ánh tên hiện hành.

Trong **graph database**, số bạn bè trên đỉnh người dùng có thể được tính từ các cạnh follow/friendship. Lưu sẵn bộ đếm đòi một nguồn chuẩn cho quan hệ và quy tắc thêm/xóa cạnh đúng.

Trong **hệ phân tích**, bảng fact/dimension hay bảng tổng hợp có thể cần các quy tắc **business effective time**, dữ liệu đến muộn và sửa hồi tố. Lineage phải truy được tới sự kiện hoặc chứng từ nguồn, không chỉ tới bảng đã tổng hợp ở bước trước.

## 14. Một quyết định thiết kế minh họa bằng bằng chứng

Giả sử trang tìm kiếm có p95 **240 ms**, mục tiêu **150 ms**. Sau khi sửa truy vấn và chỉ mục, p95 còn **162 ms**. Nhóm thử tạo **product_cards** với dữ liệu tên/giá đã chuẩn hóa để đọc một lần; p95 giảm còn **105 ms**.

**Các số liệu sau chỉ là minh họa để phân tích, không phải benchmark thực tế.**

| Chỉ tiêu tại cùng tải đại diện | Đọc nguồn + JOIN | Projection bất đồng bộ |
| --- | ---: | ---: |
| API p95 | 162 ms | 105 ms |
| SLO API | ≤ 150 ms | ≤ 150 ms |
| Độ trễ đồng bộ p95 | Không có pipeline riêng | 4 giây |
| Độ trễ xấu nhất quan sát | Không áp dụng | 38 giây |
| Giới hạn độ tươi trên UI | Giá/tên không cũ quá 30 giây | Giá/tên không cũ quá 30 giây |
| Chi phí bổ sung | Đọc từ nguồn, index | Outbox, consumer, bản sao, giám sát |
| Tính đúng | Theo nguồn ở lúc đọc | Phải chứng minh lag và version |

Projection **đạt mục tiêu độ trễ API**, nhưng **chưa đáp ứng giới hạn độ tươi tối đa 30 giây** vì đã quan sát 38 giây. Không thể duyệt triển khai chỉ dựa vào p95 đồng bộ 4 giây. Cần điều chỉnh pipeline, giảm backlog, chia luồng, hoặc thay đổi hợp đồng đọc theo nghiệp vụ rồi đo lại.

Nếu một phần trường (ví dụ nhãn danh mục) được phép chậm 60 giây nhưng **giá chốt đơn** bắt buộc xác thực nguồn, có thể phục vụ hai access pattern khác nhau: danh sách dùng projection; xác nhận thanh toán dùng nguồn giá. **Nguồn chuẩn và hợp đồng đồng bộ phải đi theo ngữ nghĩa của từng trường và mục đích đọc.**

## 15. Checklist trước khi đưa dữ liệu dẫn xuất vào vận hành

Một nhóm có thể dùng các câu hỏi sau trong buổi review lược đồ:

| Câu hỏi | Bằng chứng cần có |
| --- | --- |
| Giá trị này trả lời sự thật nghiệp vụ nào? | Định nghĩa tên trường, trạng thái và thời điểm hiệu lực |
| Ai được quyết định giá trị đúng? | Nguồn chuẩn theo field/aggregate, quyền ghi |
| Vì sao cần bản sao? | Access pattern, số liệu baseline, SLO |
| Dữ liệu dẫn xuất tính thế nào? | Công thức, filter, grain, đơn vị, locale/timezone |
| Dữ liệu có thể cũ bao lâu? | Hợp đồng consistency/freshness và cách đo |
| Thay đổi nguồn được phát ra sao? | Transaction/outbox/CDC, mọi đường ghi |
| Event có bị giao trùng hoặc sai thứ tự? | Event ID, source version, idempotent consumer |
| Bản ghi bị xóa xử lý thế nào? | Tombstone, quyền truy cập, retention |
| Ai vận hành projection? | Chủ sở hữu consumer, cảnh báo, runbook |
| Khi bị sai làm sao biết? | Đối soát theo cùng version/watermark, metric |
| Khi cần dựng lại phải làm gì? | Snapshot/checkpoint, replay, chống ghi lùi |
| Khi schema/công thức đổi phải làm gì? | Event schema version, calculation version, backfill |
| Kết quả có thể được dùng để ra quyết định gì? | Phân biệt hiển thị tham khảo với nghiệp vụ cần dữ liệu xác nhận |

**Không cần phi chuẩn hóa** nếu truy vấn từ nguồn đã đạt mục tiêu với chi phí chấp nhận được. Một bản sao làm giảm thời gian đọc nhưng không có ai chịu trách nhiệm đồng bộ có thể khiến chi phí sửa lỗi lớn hơn nhiều so với lợi ích đo được.

## 16. Bài tập tình huống

### Tình huống A — Hai nơi cùng chỉnh giá

Dịch vụ Catalog quản lý **current_price** nhưng giao diện quản trị bán hàng cũng cho sửa trực tiếp trường **price_display** trên bảng product_cards. Sáng nay Catalog ghi 180.000 VND; buổi chiều nhân viên bán hàng sửa bản sao thành 175.000 VND. Consumer sau đó nhận lại sự kiện 180.000 VND.

**Câu hỏi:** Sai ở hợp đồng nguồn nào? Nên thay đổi đường ghi thế nào?

### Tình huống B — Event trùng và đến sai thứ tự

Một sản phẩm có các phiên bản tên: v5 = “Áo xanh”, v6 = “Áo biển”. Consumer lần lượt nhận v6, v5, v6 do retry. Nếu dùng UPDATE vô điều kiện, tên cuối cùng có thể phụ thuộc thứ tự nhận.

**Câu hỏi:** Trường hợp này cần lưu metadata gì và dùng điều kiện nào để áp dụng sự kiện?

### Tình huống C — Bản ghi đã bị xóa lại xuất hiện

Search projection xóa vật lý một sản phẩm khi nhận event **ProductDeleted v9**. Sau đó, message **ProductUpdated v8** bị giao lại và consumer INSERT sản phẩm vào projection.

**Câu hỏi:** Vì sao xảy ra lỗi và có hai nhóm phương án nào để ngăn hồi sinh dữ liệu?

### Tình huống D — “Sai dữ liệu” hay “đang đồng bộ”?

Nguồn có product #501 ở version 21; projection đang ở version 20. Nhóm đặt giới hạn độ trễ 30 giây. Một người chạy đối soát và thấy version chênh lệch.

**Câu hỏi:** Đủ để kết luận lỗi chưa? Cần thêm thông tin gì để xác định vi phạm?

### Tình huống E — Địa chỉ giao hàng lịch sử

Khách đã xác nhận giao tới địa chỉ A. Sau đó khách sửa sổ địa chỉ thành B. Một job “sửa lệch” thấy **order.ship_to_address** khác **customer_addresses.current_address** và cập nhật đơn cũ thành B.

**Câu hỏi:** Job sai ở đâu? Có nên dùng cùng một bộ đối soát cho snapshot lịch sử và projection hiện hành không?

### Gợi ý lời giải

1. **A:** Catalog là nguồn chuẩn cho giá niêm yết, còn **product_cards** chỉ là bản sao. Cần dừng sửa giá trực tiếp ở projection; giao diện gửi lệnh qua nguồn có thẩm quyền. Nếu có chính sách giá bán riêng, phải mô hình hóa rõ một nguồn giá khác hoặc quy tắc hợp nhất trước khi phát projection.
2. **B:** Lưu **source_version** của từng product_id, áp dụng event chỉ khi version mới **lớn hơn** version hiện có. Điều này giúp bỏ event cũ và event lặp. Nếu event cùng version nhưng payload khác, cần cảnh báo hợp đồng nguồn.
3. **C:** Đã xóa hàng chứa version nên consumer không còn thông tin để bác bỏ v8. Có thể **giữ tombstone/is_deleted với version 9** hoặc áp dụng cơ chế lưu mốc xóa/từ chối event cũ trong kho khác; khi dọn tombstone phải xét thời gian sống của event và cách rebuild.
4. **D:** Chưa đủ; version chênh có thể là độ trễ bình thường. Cần biết thời điểm commit/độ tuổi event chưa áp dụng, checkpoint consumer, số lần retry và ngưỡng 30 giây được định nghĩa là tối đa hay phân vị. Chỉ kết luận vi phạm khi đo theo đúng hợp đồng.
5. **E:** Job dùng sai ngữ nghĩa: địa chỉ đã xác nhận là **sự thật lịch sử**, không phải bản sao của địa chỉ mặc định hiện hành. Không được so hai trường để ép bằng nhau. Kiểm chứng snapshot bằng chứng cứ đặt hàng/chỉ dẫn đã duyệt; projection hiện hành mới cần so với nguồn hiện hành theo độ trễ.

## 17. Ghi nhớ

**Nguồn dữ liệu chuẩn là quyền quyết định một sự thật nghiệp vụ; dữ liệu dẫn xuất là kết quả phục vụ một nhu cầu đọc hoặc tổng hợp.** Một số giá trị lịch sử có thể giống dữ liệu hiện hành tại lúc ghi nhưng có hợp đồng thay đổi hoàn toàn khác.

Mỗi bản sao cần trả lời được **“Lấy từ đâu, ai chịu trách nhiệm, phiên bản nào đã được áp dụng, chậm bao lâu là chấp nhận được, có thể đối soát và tái dựng không?”**. Nếu thiếu câu trả lời, việc thêm bảng/cột để đọc nhanh sẽ làm tăng rủi ro mô hình dữ liệu.

Thiết kế tốt giữ được cả **hiệu năng, ngữ nghĩa và khả năng tiến hóa**: nguồn có thẩm quyền, biến đổi có lineage, consumer đồng bộ theo hợp đồng, người dùng hiểu độ tươi dữ liệu và nhóm vận hành biết cách phát hiện cũng như khắc phục sai lệch.
