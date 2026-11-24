# Price effective period — Khoảng hiệu lực của giá

## 1. Mục tiêu và phạm vi

Price effective period là khoảng thời gian một mức giá được phép áp dụng trong một phạm vi kinh doanh cụ thể. Với bảo mật logic nghiệp vụ, lưu hai cột bắt đầu và kết thúc chưa đủ: hệ thống phải xác định **giá nào, cho ai, trong ngữ cảnh nào, được chọn tại thời điểm nào và còn được thực hiện đến khi nào**.

Bài học thuộc chương **Pricing Rules**, tập trung vào ngăn dùng giá chưa bắt đầu hoặc đã hết hạn, tự lùi thời gian mua, sửa lịch giá trái quyền, giữ giá cũ vô hạn và khai thác tranh chấp giữa báo giá với thanh toán. Các hàng rào gồm business invariants, state machine, quyền theo đối tượng, transaction, idempotency và kiểm thử ranh giới thời gian.

Sau bài học, bạn có thể:

- Định nghĩa khoảng hiệu lực không mơ hồ ở điểm bắt đầu/kết thúc.
- Phân biệt thời hạn của bảng giá, báo giá, phê duyệt và thanh toán.
- Thiết kế lịch giá tránh chồng lấn hoặc lựa chọn không xác định.
- Kiểm tra thời gian có thẩm quyền tại hàng rào thực hiện.
- Bảo vệ lịch giá và kết quả đã chốt trước sửa nội dung, retry và yêu cầu đồng thời.

Các mốc thời gian và giá trong bài là ví dụ giả định. Những quyết định như giữ giá sau khi chương trình kết thúc phải đến từ chính sách sản phẩm, không được tự suy ra từ việc client đã mở màn hình mua hàng.

## 2. Một giá trị đúng nhưng được dùng sai thời điểm

Một sản phẩm có lịch giá, trong cùng ngày và cùng múi giờ UTC:

| Khoảng | Giá |
| --- | --- |
| Trước 10:00 | 100.000 VND |
| Từ 10:00 đến trước 11:00 | 80.000 VND |
| Từ 11:00 trở đi | 100.000 VND |

Các cách lạm dụng thường gặp:

- Gửi `effectiveAt = 10:30` lúc 11:20 để máy chủ chọn lại giá khuyến mại.
- Lấy `priceId` của chương trình chưa bắt đầu rồi gọi thẳng checkout.
- Mở giỏ lúc 10:59 nhưng giữ request đến nhiều giờ sau mới thanh toán bằng giá cũ.
- Thay `expiresAt` trong payload hoặc xin gia hạn liên tục mà không định giá lại.
- Gửi request trước 11:00, để nó chờ khóa, rồi dùng kết quả kiểm tra thời gian cũ sau 11:00.
- Lạm dụng quyền vận hành để lùi ngày hiệu lực hoặc sửa số tiền của phiên bản giá đã được khách duyệt.

Không thể kết luận mọi thanh toán sau 11:00 bằng giá 80.000 đều sai. Một báo giá hợp lệ có thể được cam kết giữ đến 11:04. Điều phải kiểm tra là **cam kết nào đã được cấp và điều kiện nào cho phép thực hiện**, thay vì so thời gian với một cột bất kỳ.

## 3. Dùng khoảng nửa kín: có bắt đầu, không có kết thúc

Một quy ước rõ ràng cho lịch giá là:

```text
[start_at, end_at)

isEffective(t) = start_at <= t AND t < end_at
```

Nếu không có hạn kết thúc, chỉ kiểm tra `start_at <= t`. Khoảng hữu hạn phải thỏa `start_at < end_at`.

Hai khoảng nối tiếp:

```text
P1: [10:00, 11:00)
P2: [11:00, 12:00)
```

Tại đúng 11:00, P1 không còn hiệu lực và P2 bắt đầu. Không dùng `BETWEEN start_at AND end_at` nếu điều đó bao gồm cả hai đầu và làm hai giá cùng hợp lệ ở ranh giới.

| Thời điểm quyết định | P1 có hiệu lực? |
| --- | --- |
| Trước 10:00 | Không |
| Đúng 10:00 | Có |
| Ngay trước 11:00 ở độ chính xác lưu trữ | Có |
| Đúng 11:00 | Không |
| Sau 11:00 | Không |

Không biểu diễn cuối ngày bằng `23:59:59.999` rồi hy vọng không còn phần nhỏ hơn. Với lịch theo ngày, có thể biểu diễn kết thúc bằng đầu ngày kế tiếp, sau khi chuyển đúng múi giờ kinh doanh thành thời điểm tuyệt đối.

Cùng khoảng thời gian chưa đủ để xác định giá. Phạm vi giá còn có thể gồm tenant, SKU, currency, kênh bán, nhóm khách, loại hợp đồng và bậc số lượng. Một giá còn hạn của tenant khác hoặc dành riêng khách VIP không được áp dụng cho mọi người.

## 4. Phân biệt các mốc thời gian và các loại hiệu lực

| Trường/khái niệm | Ý nghĩa | Không được nhầm với |
| --- | --- | --- |
| `valid_from`, `valid_until` | Khoảng một mức giá được phép chọn | Thời điểm nhân viên nhập giá |
| `published_at` | Lúc cấu hình được phát hành | Lúc chương trình bắt đầu |
| `recorded_at` | Lúc hệ thống ghi nhận bản ghi/sự kiện | Ngày hiệu lực nghiệp vụ |
| `quoted_at` | Lúc server cấp báo giá | Cam kết giữ giá vô hạn |
| `quote_expires_at` | Hạn dùng báo giá theo chính sách | Hạn thanh toán ngoài hệ thống |
| `approval_expires_at` | Hạn của sự chấp thuận hoặc quyền thực hiện | Hạn của lịch giá gốc |
| `accepted_at` | Thời điểm vượt hàng rào chấp nhận lệnh | Thời điểm client bấm nút |
| `posted_at` | Lúc kết quả được ghi nhận | Thời điểm dùng để chọn lại giá lịch sử |
| `service_at` | Ngày/giờ sử dụng dịch vụ nếu sản phẩm có | Mặc định là thời điểm mua |

Một bản ghi có thể được công bố hôm nay nhưng bắt đầu tuần sau. Trạng thái `PUBLISHED` không đồng nghĩa `effective now`.

Trong bài, giá bán tức thời được chọn theo thời gian máy chủ. Với vé, thuê chỗ hoặc dịch vụ có giá theo ngày sử dụng, thời điểm định giá có thể là `service_at`. Client được đề xuất ngày sử dụng nhưng server phải kiểm tra đó là phần hợp lệ của dịch vụ đang mua; không cho dùng một `effectiveAt` tùy ý, tách rời đơn hàng, để quay về giá cũ.

Khi cần trả lời cả “giá nào có hiệu lực vào ngày X” và “hệ thống biết thông tin đó từ lúc nào”, phải lưu riêng lịch hiệu lực và lịch sử ghi nhận/thay đổi. Một cột `updated_at` không trả lời được cả hai câu hỏi. Sửa hồi tố cần quyền và quy trình riêng, không được thay lịch sử của đơn đã hoàn tất.

## 5. Thời gian có thẩm quyền và múi giờ

### 5.1. Client không quyết định đồng hồ giao dịch

Trong luồng mua tức thời, các trường như `clientNow`, timezone trình duyệt, HTTP `Date` từ phía gọi hoặc thời gian ký một request không tự quyết định giá hiện hành. Danh tính, phạm vi giá và thời điểm quyết định phải được kiểm tra ở server.

Client có thể gửi `priceId`, nhưng server phải tải mức giá đó và kiểm tra cả phạm vi, trạng thái phát hành, version và khoảng hiệu lực. ID khó đoán không phải quyền sử dụng giá.

Chọn nguồn thời gian nhất quán cho quyết định cuối, chẳng hạn đồng hồ của cơ sở dữ liệu giao dịch. Đồng bộ đồng hồ giữa các node và giám sát sai lệch vẫn cần thiết; dùng UTC chỉ giải quyết biểu diễn, không tự làm đồng hồ chính xác.

### 5.2. Chuyển giờ kinh doanh thành thời điểm tuyệt đối

Lịch do người vận hành nhập cần có timezone kinh doanh rõ ràng. Sau khi kiểm tra, chuyển sang các thời điểm tuyệt đối để so sánh, đồng thời giữ timezone/đầu vào gốc phục vụ giải thích.

Không suy timezone từ máy đang chạy tác vụ nền. Khi hệ thống phục vụ vùng có đổi giờ mùa hè, một giờ địa phương có thể không tồn tại hoặc xuất hiện hai lần; cần quy tắc chấp nhận/từ chối hay chọn offset cụ thể. Java mô tả các trường hợp gap/overlap trong [ZonedDateTime API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/ZonedDateTime.html).

Nếu giá lặp theo lịch “mỗi ngày từ 09:00 đến 17:00 tại vùng X”, lưu quy tắc lịch và timezone có quản trị, rồi xác định từng cửa sổ. Không coi một ngày lịch luôn bằng đúng 86.400 giây tại mọi vùng.

### 5.3. Độ chính xác và thời điểm lấy đồng hồ

Chuẩn hóa độ chính xác timestamp giữa API, Java, database và dữ liệu được ký. Nếu database dùng microsecond mà token chứa nanosecond, cần một quy tắc chuyển đổi thống nhất trước khi chốt nội dung; không để mỗi tầng tự làm tròn khác nhau ở ranh giới.

Trong PostgreSQL, `CURRENT_TIMESTAMP`/`now()` phản ánh thời điểm bắt đầu transaction; `statement_timestamp()` là đầu statement, còn `clock_timestamp()` lấy thời gian tại lúc gọi. Vì thế, một transaction bắt đầu trước khi giá hết hạn có thể kiểm tra sai nếu dùng timestamp đầu transaction sau một lần chờ dài. Xem [PostgreSQL — Current Date/Time](https://www.postgresql.org/docs/18/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT).

Lấy một thời điểm quyết định phù hợp sau khi chờ các khóa cần thiết, dùng nó nhất quán cho hàng rào cuối và lưu lại. Không lấy thời gian ở API rồi mang nguyên giá trị đó qua mọi lần retry hoặc chờ hàng đợi.

## 6. Hai chính sách báo giá cần phân biệt

### 6.1. Giá phải còn hiệu lực tại lúc chấp nhận

Với chính sách chặt theo cửa sổ chương trình, báo giá không được sống quá hạn giá nguồn:

```text
quote_expires_at = min(
    quoted_at + allowed_quote_ttl,
    source_price_valid_until,
    other_required_deadlines
)
```

Giá được chọn lúc 10:59:50, chương trình kết thúc 11:00 và TTL tối đa 5 phút thì quote chỉ dùng đến trước 11:00. Báo giá không tự tạo ngoại lệ cho chương trình.

### 6.2. Cam kết giữ giá của quote

Một sản phẩm khác có thể cho phép cấp quote trong thời gian chương trình, rồi giữ giá thêm 5 phút:

```text
quoted_at = 10:59:50
source_price_valid_until = 11:00:00
quote_expires_at = 11:04:50
```

Thực hiện lúc 11:02 có thể hợp lệ nếu quote được cấp đúng điều kiện, còn hạn, chưa dùng và chưa bị thu hồi theo hợp đồng đã định nghĩa. Đây là cam kết giá riêng, không phải bằng chứng rằng bảng giá cũ vẫn còn hiệu lực.

Chính sách quote cần định nghĩa khả năng thu hồi, điều kiện hết hạn, giới hạn số lượng và phạm vi đảm bảo. Giữ giá không tự giữ hàng, giữ hạn mức khuyến mại hoặc kéo dài quyền ghi nợ. Các tài nguyên đó có trạng thái/thời hạn riêng và phải được phối hợp.

### 6.3. Không gia hạn giá cũ bằng thao tác kỹ thuật

Không làm mới `quoted_at` hoặc `expires_at` mỗi lần client mở giỏ, heartbeat hoặc retry. Một báo giá mới phải được định giá và cấp quyền theo điều kiện đang áp dụng, hoặc đi qua nghiệp vụ gia hạn được cho phép rõ ràng.

Có thể hạn chế số quote đang mở, số lượng hàng và ngân sách được giữ theo chính sách để chống gom quote nhằm giữ lợi ích quá mức. Các bộ đếm dùng chung phải được bảo vệ trước yêu cầu đồng thời; giới hạn trong bộ nhớ từng node không đủ cho một cam kết toàn hệ thống.

Quote cần gắn ít nhất với:

```text
quote_id, tenant_id, authorized_subject
order/cart ID + content version
SKU, quantity, channel, customer eligibility
price_scope_id, price_period_id, pricing_policy_version
currency, unit_price_minor, discount, tax, fees, total_minor
quoted_at, not_before, expires_at
state, consumed_by_order_id
```

Nếu dùng token có chữ ký, chữ ký bảo vệ tính toàn vẹn của nội dung. Nó không tự ngăn dùng lại, không kiểm tra quyền hiện tại và không thay trạng thái thu hồi/tiêu thụ khi nghiệp vụ cần. Không tin bản sao unsigned của cùng các trường do client gửi kèm.

## 7. Ví dụ Java cho khoảng hiệu lực

Đoạn mã minh họa dùng `Instant` và quy ước `[start, end)`. Hạn cuối `null` có nghĩa không giới hạn trên trong mô hình này.

```java
import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

record EffectivePeriod(Instant startsAt, Instant endsAt) {
    EffectivePeriod {
        Objects.requireNonNull(startsAt, "startsAt");
        if (endsAt != null && !startsAt.isBefore(endsAt)) {
            throw new IllegalArgumentException("Invalid effective period");
        }
    }

    boolean contains(Instant decisionAt) {
        Objects.requireNonNull(decisionAt, "decisionAt");
        return !decisionAt.isBefore(startsAt)
                && (endsAt == null || decisionAt.isBefore(endsAt));
    }
}

final class PriceTimeGate {
    private final Clock clock;

    PriceTimeGate(Clock clock) {
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    boolean isEffective(EffectivePeriod period) {
        Instant decisionAt = clock.instant();
        return period.contains(decisionAt);
    }
}
```

Trong một quyết định có nhiều điều kiện, lấy `decisionAt` một lần ở đúng vị trí rồi truyền cho các phép kiểm tra liên quan. Không gọi `now()` ở mỗi dòng và để một số điều kiện dùng trước ranh giới, số còn lại dùng sau ranh giới.

Có thể truyền `Clock.fixed(...)` để kiểm thử đúng điểm bắt đầu, đúng điểm kết thúc hoặc ngay trước kết thúc mà không cần chờ thời gian thực. `Clock` hỗ trợ thay nguồn thời gian phục vụ kiểm thử; bản thân nó không bảo đảm một quyết định là có thẩm quyền. Xem [Java Clock API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html).

Đoạn mã chưa kiểm tra trạng thái published, khách hàng được hưởng giá, tenant, số tiền hoặc tranh chấp dữ liệu. Kiểm tra ở application giúp thiết kế dễ hiểu; hàng rào thực hiện và trạng thái dùng một lần vẫn phải được bảo vệ tại nơi ghi dữ liệu.

## 8. Viết bất biến theo chính sách đã chọn

| Mã | Bất biến | Cách bảo vệ |
| --- | --- | --- |
| P1 | Tối đa một mức giá được chọn trong cùng scope tại một thời điểm | Lịch không chồng lấn hoặc quy tắc ưu tiên tường minh |
| P2 | Giá được chọn đúng tenant, SKU, currency và điều kiện khách hàng | Server xác định scope và kiểm tra quyền/điều kiện |
| P3 | Chỉ mức giá đã phát hành được dùng để cấp quote | Workflow phát hành và quyền theo đối tượng |
| P4 | Thời điểm lựa chọn/thực hiện đến từ nguồn có thẩm quyền | Không tin timestamp tự khai của client |
| P5 | Lệnh mới không tiêu thụ quote ngoài khoảng cho phép | Kiểm tra cuối và chuyển trạng thái có điều kiện |
| P6 | Nội dung thực hiện khớp nội dung đã được giữ giá và duyệt | Snapshot bất biến, version và fingerprint |
| P7 | Mỗi quote dùng một lần theo hợp đồng của ví dụ | Khóa/chuyển trạng thái và ràng buộc nghiệp vụ |
| P8 | Retry của kết quả đã commit không tạo giao dịch mới | Idempotency bền vững và kết quả gốc |
| P9 | Thay đổi lịch không âm thầm sửa đơn đã chấp nhận | Snapshot của đơn và dấu vết thay đổi lịch |
| P10 | Lỗi thời hạn hoặc điều kiện không để lại biến động tiền một phần | Transaction cho toàn bộ hiệu ứng cục bộ |

“Trong cùng scope” phải được định nghĩa đầy đủ. Nếu vừa có giá thường vừa có giá hợp đồng có thể khớp khách hàng, cần một quy tắc chọn mức ưu tiên được phê duyệt. Không lấy mức thấp nhất hoặc bản ghi mới nhất chỉ vì truy vấn trả nhiều dòng.

Một mô hình chọn giá cơ sở duy nhất có thể cấm chồng lấn. Một mô hình giá cơ sở cộng khuyến mại lại có các tầng độc lập; các tầng được phép trùng thời gian không nên bị cấm một cách máy móc. Phải kiểm soát thứ tự áp dụng và khả năng kết hợp của từng tầng.

## 9. Minh họa lịch giá không chồng lấn bằng PostgreSQL

Schema sau dành cho mô hình **một giá cơ sở được công bố trong một scope**, chưa mô tả các tầng khuyến mại. Scope mẫu gồm SKU, currency, kênh và segment; nếu sản phẩm có bậc số lượng hoặc hợp đồng riêng, chúng phải có biểu diễn tương ứng trong phạm vi chọn giá.

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE pricing_scope (
    tenant_id UUID NOT NULL,
    scope_id UUID NOT NULL,
    sku_id UUID NOT NULL,
    currency VARCHAR(3) NOT NULL,
    channel TEXT NOT NULL,
    segment_key TEXT NOT NULL,
    schedule_revision BIGINT NOT NULL DEFAULT 0,
    revocation_epoch BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, scope_id),
    UNIQUE (tenant_id, sku_id, currency, channel, segment_key)
);

CREATE TABLE price_period (
    tenant_id UUID NOT NULL,
    price_period_id UUID NOT NULL,
    scope_id UUID NOT NULL,
    unit_price_minor BIGINT NOT NULL CHECK (unit_price_minor >= 0),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ,
    publication_state TEXT NOT NULL
        CHECK (publication_state IN ('DRAFT', 'PUBLISHED')),
    effective_window TSTZRANGE GENERATED ALWAYS AS (
        tstzrange(valid_from, valid_until, '[)')
    ) STORED,
    PRIMARY KEY (tenant_id, price_period_id),
    FOREIGN KEY (tenant_id, scope_id)
        REFERENCES pricing_scope(tenant_id, scope_id),
    CHECK (isfinite(valid_from)),
    CHECK (valid_until IS NULL OR
           (isfinite(valid_until) AND valid_from < valid_until)),
    EXCLUDE USING gist (
        tenant_id WITH =,
        scope_id WITH =,
        effective_window WITH &&
    ) WHERE (publication_state = 'PUBLISHED')
);
```

`tstzrange` biểu diễn khoảng thời gian có timezone; exclusion constraint kết hợp toán tử chồng lấn `&&` ngăn các khoảng được công bố trùng nhau trong cùng scope. Xem [PostgreSQL — Range Types](https://www.postgresql.org/docs/18/rangetypes.html). Extension [btree_gist](https://www.postgresql.org/docs/18/btree-gist.html) hỗ trợ các thành phần so sánh scalar như UUID trong chỉ mục ghép này.

Giá zero được schema cho phép để minh họa sản phẩm có hàng miễn phí; nếu nghiệp vụ cấm hoặc cần phê duyệt riêng, bổ sung điều kiện tương ứng. Registry currency, quyền thay đổi giá, audit và quản lý version đầy đủ chưa được biểu diễn trong schema rút gọn.

Truy vấn chọn giá dùng thời điểm có thẩm quyền:

```sql
SELECT p.price_period_id, p.unit_price_minor, s.currency,
       p.valid_from, p.valid_until, s.schedule_revision
FROM price_period AS p
JOIN pricing_scope AS s
  ON s.tenant_id = p.tenant_id AND s.scope_id = p.scope_id
WHERE p.tenant_id = :verified_tenant_id
  AND p.scope_id = :server_resolved_scope_id
  AND p.publication_state = 'PUBLISHED'
  AND p.effective_window @> CAST(:decision_at AS timestamptz);
```

Kỳ vọng đúng một mức giá cho scope được yêu cầu. Không có giá thì dừng định giá hoặc áp dụng fallback đã được chính sách quy định rõ. Không chọn một giá đã hết hạn để lấp chỗ trống. Nhiều kết quả là lỗi bất biến cần xử lý, không thêm `ORDER BY ... LIMIT 1` để che dữ liệu mâu thuẫn.

Exclusion constraint ngăn chồng lấn, không bảo đảm lịch không có khoảng trống. Nếu sản phẩm cần bán liên tục, quy trình phát hành phải kiểm tra độ phủ của lịch trong chân trời đã cam kết. Các scope khác nhau cũng có thể cùng khớp một khách hàng; điều đó cần được giải quyết ở quy tắc routing/ưu tiên.

Để chuyển một mức giá không hạn cuối sang giá mới, đóng khoảng cũ và công bố khoảng mới trong cùng transaction. Các thao tác phát hành phải khóa cùng bản ghi scope hoặc có giao thức tương đương. Không thực hiện “kiểm tra chưa trùng” rồi ghi bằng hai bước không có ràng buộc và kiểm soát đồng thời.

Số tiền và nội dung giá đã phát hành không được sửa tùy ý. Việc thay lịch tương lai hoặc kết thúc sớm cần version/audit và quy trình có quyền; lịch sử đã dùng để chấp nhận đơn phải còn truy vết được. DDL trên không tự triển khai toàn bộ chính sách bất biến hay lịch sử hai chiều thời gian.

## 10. Hàng rào chấp nhận phải nằm sau các lần chờ khóa

Giả sử quote hết hạn lúc 11:00:

```text
10:59:59  Request đến API, kiểm tra sơ bộ thấy còn hạn
10:59:59  Request chờ khóa của quote hoặc order
11:00:03  Khóa được cấp
11:00:03  Hàng rào cuối phải dùng thời gian mới
```

Nếu hợp đồng là phải được chấp nhận trước 11:00, request trên không được thực hiện như một lệnh mới. Việc đến gateway hoặc bắt đầu transaction trước hạn không đồng nghĩa đã được chấp nhận.

Một luồng thiết kế có thể là:

```text
acceptPricedOrder(actor, quoteId, approvalId, key):
    requireAuthenticated(actor)
    validateCommandShape()

    begin transaction
        command = canonicalCommandFromVerifiedContext(actor, IDs)
        idem = claimOrLoadIdempotency(actor, operation, key)
        requireSameFingerprintIfExisting(idem, command)

        order = lockOrderInVerifiedTenant()
        requireActorMayAccessOrder(actor, order)
        if idem has a committed result:
            requireActorMayReadResult(actor, idem.result)
            commit and return stored result

        quote = lockQuote(quoteId)
        approval = lockApproval(approvalId)
        lockRelevantPricingControlAndPermissionState()
        lockMoneyInventoryAndLimitStateInStableOrder()

        requireQuoteBelongsToActorAndOrder(quote, actor, order)
        requireExactContentVersionAndMoneyMatch(order, quote, approval)
        requireCurrentPermissionsAndEligibility()
        requirePriceGuaranteePolicyAndRevocationStateAllow(quote)
        requireOtherResourcesReadyForAcceptance()

        accepted = consumeQuoteOnceAtFreshAuthoritativeTime()
        requireExactlyOneRowConsumed(accepted)
        requireOtherDeadlineGuardsAtSameDecisionPoint(accepted.at)

        createImmutableOrderPriceSnapshot(quote, accepted.at)
        applyLocalMoneyAndResourceEffects()
        appendBalancedLedgerIfMoneyIsPosted()
        markApprovalConsumedAndOrderAccepted()
        appendOutboxEvent()
        saveIdempotencyResult(idem)
    commit
    return committed result
```

Thứ tự khóa cụ thể cần được chọn thống nhất cho toàn hệ thống. Các đường hủy, thu hồi, phát hành và thực hiện phải phối hợp trên dữ liệu chung, không mỗi đường khóa một thứ tự khác nhau. Các điều kiện trên đối tượng có thể thay đổi phải được bảo vệ bằng khóa hoặc version phù hợp.

### Chuyển quote có điều kiện tại một mốc quyết định

Ví dụ PostgreSQL dưới đây giả định **quote và các bản ghi điều khiển cần thiết đã được khóa trong transaction**, các kiểm tra tốn thời gian đã hoàn thành. Tên cột minh họa những trường cần có trên bảng quote.

```sql
WITH gate AS MATERIALIZED (
    SELECT clock_timestamp() AS decision_at
)
UPDATE price_quote AS q
SET state = 'CONSUMED',
    accepted_at = gate.decision_at,
    consumed_by_order_id = :verified_order_id
FROM gate
WHERE q.tenant_id = :verified_tenant_id
  AND q.quote_id = :quote_id
  AND q.subject_id = :verified_subject_id
  AND q.order_content_version = :approved_content_version
  AND q.state = 'ISSUED'
  AND q.not_before <= gate.decision_at
  AND gate.decision_at < q.expires_at
  AND q.revocation_epoch = :current_locked_revocation_epoch
RETURNING q.quote_id, q.accepted_at, q.currency, q.total_minor;
```

Các tham số về chủ thể, version và epoch lấy từ dữ liệu đã xác minh/khóa, không lấy trực tiếp từ client. Cần đúng một dòng trả về; không có dòng thì không tiếp tục hiệu ứng tiền.

Nếu chưa khóa quote trước, mốc lấy trong CTE có thể xuất hiện trước một lần chờ khóa của chính UPDATE. Không sao chép câu lệnh rồi bỏ tiền điều kiện về khóa và vị trí lấy thời gian. `MATERIALIZED` giúp dùng một giá trị gate nhất quán trong ví dụ, không tự giải quyết mọi tranh chấp.

Epoch ở ví dụ là cơ chế thu hồi theo chính sách. Không tăng nó cho mọi thay đổi lịch thông thường nếu cam kết giữ giá yêu cầu tôn trọng quote cũ. Quyền thu hồi khẩn cấp, phạm vi ảnh hưởng và luồng cập nhật epoch phải được định nghĩa riêng và phối hợp cùng hàng rào này.

### Chấp nhận trước hạn khác với commit trước hạn

Điều kiện tại gate chứng minh lệnh được chấp nhận ở thời điểm ghi nhận trong transaction thành công. Nó không chứng minh commit, capture bên ngoài hoặc giao hàng đều hoàn tất trước hạn giá. Một kiểm tra `now < expires_at` không bảo đảm những mốc khác đó.

Nếu transaction rollback thì việc tiêu thụ quote cũng rollback. Retry phải kiểm tra lại nếu chưa có kết quả commit. Nếu đã commit và response bị mất, retry chỉ trả kết quả cũ; không coi quote đã dùng/hết hạn là lý do tạo một thanh toán mới.

## 11. Phát hành, đổi lịch và thu hồi giá

Lịch giá có thể cho phép nhiều bản nháp, nhưng chỉ cấu hình được duyệt mới được công bố. Quyền nên xét cả tenant, SKU/scope và loại thao tác, thay vì chỉ có role chung `ADMIN`.

Một quy trình phát hành có thể yêu cầu:

1. Kiểm tra người có quyền sửa và người có quyền phê duyệt theo chính sách; nếu cần tách vai trò thì không cho tự duyệt.
2. Kiểm tra tiền tệ, miền giá, thời gian, độ phủ và xung đột trong cùng scope.
3. Kiểm tra version lịch mà người vận hành đã đọc, tránh ghi đè thay đổi của người khác.
4. Khóa scope, cập nhật các khoảng liên quan, tăng schedule revision và ghi audit trong một transaction.
5. Phát sự kiện thay đổi qua outbox để cập nhật cache và các bản đọc.

Ngày bắt đầu trong quá khứ hoặc thay đổi hồi tố cần quyền/quy trình riêng. Không cho client tùy chọn `overrideEffectiveAt` để nhân viên hỗ trợ biến một giao dịch mới thành giao dịch thuộc thời kỳ giá cũ.

Nếu phải thu hồi một mức giá sai, phân biệt tác động lên việc cấp quote mới với các quote đã cam kết. Có thể dừng cấp mới nhưng vẫn tôn trọng quote đã cấp; cũng có thể cần thu hồi theo một điều khoản được xác định trước. Hệ thống phải biểu đạt được hai hành vi, không âm thầm sửa amount của quote.

Lệnh publish cạnh tranh với quote issuance phải có thứ tự hiệu lực rõ ràng. Nếu yêu cầu là không được cấp quote mới từ lịch đã bị thay thế, cả hai luồng cần đọc/khóa revision hoặc cơ chế điều phối tương đương tại điểm cấp quote. Đọc bản sao trễ rồi ghi quote có thể bỏ qua thay đổi.

## 12. Cache, hàng đợi và thanh toán bất đồng bộ

### Cache không phải hàng rào quyền sử dụng giá

Cache cần chứa scope, revision và khoảng hiệu lực, không chỉ `SKU -> unitPrice`. TTL có thể được cắt ở ranh giới lịch gần nhất nhưng không thay việc kiểm tra thời gian và điều kiện tại server.

Một giá được cache 10 phút lúc 10:58 không tự được phép dùng đến 11:08 khi chương trình kết thúc 11:00. Invalidation giúp giảm dữ liệu cũ nhưng có thể đến muộn hoặc bị phát lại; kiểm tra gate vẫn cần dữ liệu có thẩm quyền hoặc cam kết quote hợp lệ.

Read replica phù hợp cho hiển thị theo độ trễ được chấp nhận, nhưng không nên tự quyết định quyền mới từ dữ liệu cũ nếu chính sách yêu cầu thu hồi/phát hành có hiệu lực ngay. Cache key cũng phải phân biệt currency, segment, kênh và phiên bản liên quan.

### Hàng đợi không tự giữ giá

Request được enqueue trước hạn nhưng worker chạy sau hạn vẫn phải tuân thủ mốc chấp nhận đã định nghĩa. Muốn đảm bảo giá ngay khi nhận vào hàng đợi, phải có bước chấp nhận bền vững và giữ cam kết/tài nguyên theo chính sách tại thời điểm đó. Một timestamp do producer tự khai không tạo ra cam kết.

Retry job dùng cùng intent/quote và định danh nghiệp vụ. Không xin lại quote giá cũ bằng cách tái sử dụng `quoted_at` hoặc đổi `expires_at` trong message. Consumer kiểm tra version và trạng thái nguồn thay vì tin hoàn toàn bản sao trong hàng đợi.

### Thanh toán đến sau khi giá nguồn kết thúc

Nếu đơn đã được chấp nhận hợp lệ và giữ giá, callback sau khi lịch giá kết thúc có thể hoàn tất đơn theo snapshot gốc, trong hạn thanh toán riêng. Không định giá lại theo bảng hiện tại chỉ vì callback đến muộn.

Ngược lại, một lệnh chưa được chấp nhận không được hợp thức hóa bằng thời điểm trên màn hình client hoặc một sự kiện không gắn đúng payment attempt. Đối chiếu merchant, reference, currency, amount và trạng thái tiền có thẩm quyền. Kết quả bên ngoài chưa biết cần đối soát; không tạo charge mới chỉ vì giá/quote trước đã hết hạn sau timeout.

Thời hạn thanh toán, thời hạn giữ hàng và thời hạn quote cần trạng thái riêng. Gia hạn một hạn không được âm thầm gia hạn tất cả. Đơn đã chấp nhận nhưng quá hạn thanh toán có thể cần hủy hoặc báo giá lại theo workflow đã định nghĩa.

## 13. Các kiểu tấn công và hàng rào tương ứng

| Thao tác | Lỗi thiết kế | Hàng rào |
| --- | --- | --- |
| Gửi thời gian quá khứ | Tin `effectiveAt` ở luồng mua tức thời | Dùng thời gian/ngữ cảnh có thẩm quyền |
| Chọn giá tương lai bằng ID | Chỉ kiểm tra giá tồn tại | Kiểm tra trạng thái, scope và khoảng hiệu lực |
| Sửa amount hoặc expiresAt của quote | Tin bản sao do client gửi | Dữ liệu server hoặc token toàn vẹn kèm kiểm tra trạng thái |
| Mở giỏ để giữ giá vô hạn | Không có cam kết/TTL rõ ràng | Quote có hạn, ràng buộc nội dung và quy tắc gia hạn |
| Spam quote lúc cuối chương trình | Không giới hạn tài nguyên cam kết | Giới hạn số lượng/ngân sách và kiểm soát đồng thời |
| Đổi SKU/quantity sau khi lấy quote | Quote không gắn nội dung | ID/version, fingerprint và phê duyệt lại |
| Chờ khóa qua hạn rồi thực hiện | Kiểm tra thời gian quá sớm | Gate sau lần chờ cần thiết |
| Dùng epoch/revision cũ sau thu hồi | Chỉ đọc cache/replica | Giao thức thu hồi và kiểm tra phiên bản có thẩm quyền |
| Phát lại quote với key mới | Chỉ chống trùng theo request key | Quote dùng một lần và unique theo nghiệp vụ |
| Hai người cùng publish lịch chồng | Check-then-insert không khóa/ràng buộc | Khóa scope, revision và constraint phù hợp |
| Truy cập giá hợp đồng người khác | Chỉ kiểm tra thời gian | Quyền theo đối tượng và điều kiện khách hàng |

Nếu đồng hồ bị lùi hoặc sai lệch lớn, cần phát hiện và xử lý theo chính sách vận hành. Không mở lại quote đã ở trạng thái terminal như `EXPIRED` hoặc `CONSUMED` chỉ vì một node hiện đọc thời gian sớm hơn. Đồng hồ đơn điệu có ích để đo khoảng thời gian trong một tiến trình, nhưng không tự thay thế thời điểm tuyệt đối đã lưu và chia sẻ giữa nhiều máy.

## 14. Đặc tả kiểm thử tình huống tấn công logic

Các ca sau là hướng dẫn xây dựng test khi triển khai, không phải báo cáo đã chạy. Kiểm tra cả mức giá được chọn, state, accepted_at, snapshot đơn, biến động tiền và kết quả retry.

| Ca thử | Thiết lập/thao tác | Kết quả bắt buộc |
| --- | --- | --- |
| Trước bắt đầu | `t < start_at` | Không chọn giá đó |
| Đúng bắt đầu | `t = start_at` | Giá được chọn nếu các điều kiện khác hợp lệ |
| Ngay trước kết thúc | Mốc cuối trước end ở độ chính xác đã chọn | Giá vẫn có hiệu lực |
| Đúng kết thúc | `t = end_at` | Giá cũ không còn được chọn |
| Hai khoảng kề nhau | P1 kết thúc đúng lúc P2 bắt đầu | Chỉ P2 khớp tại ranh giới |
| Khoảng sai | Start bằng hoặc sau end | Không phát hành |
| Không hạn cuối | End không có, t sau start | Có hiệu lực theo trạng thái và phạm vi |
| Khoảng chồng | Hai lịch published cùng scope | Constraint/workflow từ chối công bố chồng |
| Khoảng trống | Không có giá khớp | Không tự dùng giá hết hạn hoặc giá tương lai |
| Client lùi thời gian | Gửi `effectiveAt` cũ trong mua tức thời | Không thay nguồn thời gian định giá |
| Scope ngoài quyền | Giá VIP/tenant khác vẫn còn hạn | Không áp dụng cho chủ thể không đủ điều kiện |
| Strict-window quote | Cấp sát cuối chương trình, thực hiện sau end | Từ chối lệnh mới |
| Guaranteed quote | Cấp hợp lệ, thực hiện sau end nguồn nhưng trước quote expiry | Chấp nhận nếu hợp đồng giữ giá và điều kiện khác cho phép |
| Chờ khóa qua hạn | Request vào trước hạn, gate chạy sau hạn | Từ chối lệnh mới theo thời điểm gate |
| Retry sau commit | Kết quả đã commit, nay quote đã hết hạn | Trả kết quả cũ, không ghi nợ thêm |
| Retry trước commit | Lần trước rollback, nay đã hết hạn | Kiểm tra lại và không tạo chấp nhận muộn |
| Key cũ đổi nội dung | Đổi quote, order version hoặc amount | Xung đột, không thực hiện nội dung mới |
| Hai execute song song | Cùng quote, key khác nhau | Tối đa một lần tiêu thụ/biến động nghiệp vụ |
| Cache còn giá cũ | Cache chưa invalidated sau ranh giới | Gate không cấp quyền sai từ cache |
| Lịch bị sửa đồng thời | Publish/thu hồi cạnh tranh cấp quote hoặc execute | Tuân thủ thứ tự hiệu lực và hợp đồng giữ giá đã định nghĩa |
| Múi giờ bất thường | Local time gap/overlap của vùng hỗ trợ | Xử lý đúng quy tắc đã chọn, không tự suy offset |
| Khác precision | API và database có độ chính xác khác nhau | Hành vi ranh giới khớp quy tắc chuẩn hóa |
| Callback muộn | Đơn đã nhận giá, callback trong hạn thanh toán riêng | Dùng snapshot gốc, không định giá lại tùy tiện |

Dùng `Clock.fixed` hoặc nguồn thời gian kiểm soát được cho test domain. Test tích hợp cần kiểm tra cách database lấy thời gian, độ chính xác và hành vi chờ khóa; chỉ mock `Clock` Java không chứng minh được SQL gate.

Tạo tranh chấp bằng barrier hoặc điều phối transaction, không chỉ thêm `sleep` rồi chờ hết hạn trong thời gian thực. Phép thử cùng quote nhưng hai key khác nhau kiểm chứng hàng rào nghiệp vụ; phép thử cùng key kiểm chứng idempotency. Hai nhóm không thay thế nhau.

## 15. Nhật ký và rà soát thiết kế

Một quyết định giá cần giải thích được:

```text
actor/workload + tenant
  -> SKU, quantity, channel, customer eligibility
  -> scope + schedule revision
  -> price period + valid interval
  -> quote + content version + guarantee policy
  -> authoritative decision time + accepted_at
  -> approval, order snapshot, posting/payment attempt
  -> idempotency result
```

Lưu lý do từ chối như `PRICE_NOT_YET_EFFECTIVE`, `PRICE_PERIOD_ENDED`, `NO_APPLICABLE_PRICE`, `AMBIGUOUS_PRICE`, `QUOTE_EXPIRED`, `QUOTE_CONTENT_CHANGED`, `QUOTE_REVOKED` hoặc `PRICE_SCOPE_NOT_ALLOWED`. Phản hồi ngoài API cần tránh lộ giá hợp đồng hoặc dữ liệu tenant khác; audit nội bộ giữ chi tiết theo quyền truy cập.

Quan sát nhiều request sát hạn, nhiều lần gia hạn, lượng quote chưa dùng bất thường, nhiều giao dịch cố lùi thời gian và độ trễ giữa received_at với accepted_at. Đây là tín hiệu để phân tích cùng chính sách, không phải bằng chứng độc lập rằng người dùng gian lận.

Khi rà soát, xác định được:

1. Mốc thời gian nào dùng để chọn giá và mốc nào dùng để chấp nhận lệnh.
2. Quy ước biên, timezone, precision và nguồn đồng hồ có thẩm quyền.
3. Scope, quy tắc ưu tiên và cách xử lý lịch trùng hoặc thiếu giá.
4. Quote có giữ giá sau hạn nguồn không, có được thu hồi/gia hạn không.
5. Điểm khóa, kiểm tra cuối và chuyển trạng thái trong transaction.
6. Kết quả của retry, callback muộn và thay đổi lịch sau khi đơn đã chấp nhận.

Khoảng hiệu lực của giá cần được thực thi như một quy tắc nghiệp vụ có phạm vi và điểm quyết định rõ ràng. Khi lịch giá, cam kết quote và snapshot đơn được tách đúng vai trò, việc đổi timestamp hoặc trì hoãn request không còn đủ để tự kéo dài một mức giá ngoài quyền được cấp.
