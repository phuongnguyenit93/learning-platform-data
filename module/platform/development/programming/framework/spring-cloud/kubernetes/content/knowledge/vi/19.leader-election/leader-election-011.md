# Tính lũy đẳng, fencing và bảo vệ tác dụng phụ quan trọng

## 1. Bầu leader là điểm bắt đầu của việc bảo vệ dữ liệu

Trong Spring Cloud Kubernetes, bầu leader giúp chọn một bản sao ứng dụng chịu trách nhiệm cho công việc điều phối: tạo hóa đơn theo kỳ, phát lệnh đồng bộ hoặc quét các bản ghi chờ xử lý. Tuy nhiên, tác dụng phụ như ghi sổ, phát hành hóa đơn và gửi yêu cầu thanh toán cần được bảo vệ ngay tại nơi chúng được thực hiện.

Bài học thuộc chương **Bầu leader** của module **SPRING_CLOUD_KUBERNETES**. Mục tiêu là thiết kế công việc vẫn đúng khi Pod tạm dừng, mạng bị chia cắt, request bị gửi lại hoặc leadership chuyển sang Pod khác. DiscoveryClient và Spring Cloud LoadBalancer giúp tìm và gọi dịch vụ; chúng không quyết định một lệnh nghiệp vụ đã được thực hiện hay chưa.

Sau bài học, bạn cần giải thích và vận dụng được ba lớp bảo vệ:

- **Tính lũy đẳng — idempotency:** cùng một ý định nghiệp vụ được gửi lại nhưng không tạo thêm kết quả nghiệp vụ.
- **Fencing:** bên nhận từ chối lệnh của phiên điều phối đã bị thay thế.
- **Giao dịch và bàn giao bền vững:** dữ liệu nghiệp vụ và ý định phát tác dụng phụ được ghi nhất quán, có khả năng phục hồi sau lỗi.

Ví dụ xuyên suốt là dịch vụ phát hành hóa đơn. Nhiều Pod có thể chạy, một Pod điều phối, PostgreSQL lưu hóa đơn và outbox, còn dịch vụ bên ngoài thực hiện bước phát hành thực tế.

## 2. Vì sao leader cũ vẫn có thể gây tác dụng phụ?

Xét một lần chuyển leader:

| Thời điểm | Pod A | Pod B | Hệ thống nhận lệnh |
| --- | --- | --- | --- |
| T0 | Là leader, chuẩn bị lệnh phát hành hóa đơn | Chờ | Chưa nhận lệnh |
| T1 | Dừng lâu vì GC hoặc mất kết nối API server | Tiếp tục tham gia bầu chọn | Có thể vẫn truy cập được từ A |
| T2 | Chưa xử lý được thông báo mất leadership | Được bầu làm leader | Nhận lệnh từ B |
| T3 | Chạy tiếp hoặc request cũ đến muộn | Đang xử lý công việc mới | Có thể nhận thêm lệnh từ A |

Mất kết nối tới Kubernetes API server không đồng nghĩa mất kết nối tới cơ sở dữ liệu hay nhà cung cấp thanh toán. Tương tự, Pod chuyển sang NotReady không thu hồi một request đã gửi ra ngoài.

Một kiểm tra như sau có khoảng trống giữa kiểm tra và sử dụng:

```java
if (localLeaderFlag.get()) {
    paymentClient.charge(command);
}
```

Sau khi đọc cờ và trước khi dịch vụ thanh toán nhận request, Pod có thể đã mất leadership. Việc kiểm tra lại Lease trước mỗi request cũng không tạo giao dịch nguyên tử giữa Kubernetes và dịch vụ thanh toán.

Tài liệu mã nguồn chính thức của Kubernetes client-go nêu rõ cơ chế bầu leader của nó không bảo đảm fencing. Đây là giới hạn cần hiểu khi xây dựng tác dụng phụ quan trọng, dù ứng dụng Java sử dụng thư viện client khác. [Nguồn: Kubernetes client-go](https://github.com/kubernetes/client-go/blob/master/tools/leaderelection/leaderelection.go).

## 3. Phân biệt ba câu hỏi độc lập

| Cơ chế | Câu hỏi nó trả lời | Điều còn cần bảo vệ |
| --- | --- | --- |
| Bầu leader | Pod nào nên điều phối công việc lúc này? | Request cũ, retry và trạng thái nghiệp vụ |
| Idempotency | Ý định nghiệp vụ này đã được thực hiện chưa? | Lệnh khác của một phiên leader cũ |
| Fencing | Phiên gửi lệnh này còn được phép ghi không? | Gửi lại cùng lệnh trong phiên hợp lệ |
| Giao dịch | Các thay đổi dữ liệu liên quan có cùng thành công hoặc cùng hủy không? | Tác dụng phụ nằm ngoài cơ sở dữ liệu |
| Outbox và xử lý trùng ở bên nhận | Ý định đã commit được chuyển đi và xử lý lại thế nào? | Giới hạn hợp đồng của từng hệ thống đích |

Ví dụ, A có epoch 41 và B có epoch 42:

- Cả A lẫn B cùng gửi lệnh phát hành hóa đơn `INV-2026-11-001`: khóa lũy đẳng giúp nhận ra cùng một ý định.
- A gửi lệnh mới cho `INV-2026-11-002` sau khi bị thay thế: khóa lũy đẳng chưa tồn tại nên không tự chặn được; cần fencing.
- B gửi lại một lệnh vì timeout: epoch vẫn hợp lệ nên fencing không tự chống trùng; cần idempotency.

Một mã UUID nhận diện request không tự giải quyết hai câu hỏi trên. Ý nghĩa của mã và cách bên nhận lưu, kiểm tra, cập nhật nó mới tạo ra bảo đảm.

## 4. Thiết kế khóa lũy đẳng theo ý định nghiệp vụ

### 4.1. Khóa phải sống qua retry và chuyển leader

Với thao tác phát hành một hóa đơn cho một tenant, có thể dùng cấu trúc:

```text
issue-invoice:v1:<tenant-id>:<invoice-id>
```

Các thành phần định danh phải được mã hóa không nhập nhằng. Trong ví dụ SQL bên dưới, tenant và invoice chỉ nhận chữ, số, dấu gạch ngang và dấu gạch dưới, nên dấu hai chấm phân tách an toàn.

Không đưa các giá trị sau vào khóa của cùng một ý định:

- Tên Pod hoặc Pod UID.
- Epoch của leader.
- Số lần retry.
- Thời điểm gửi request.
- UUID mới sinh cho từng lần thử.

Nếu A và B dùng hai khóa khác nhau chỉ vì leader thay đổi, hệ thống đích có thể coi đó là hai lần phát hành hợp lệ. Ngược lại, UUID được tạo một lần, lưu bền vững cùng ý định và dùng lại qua mọi lần thử có thể là khóa hợp lệ.

Với công việc định kỳ, dùng kỳ nghiệp vụ đã xác định rõ múi giờ, chẳng hạn `tenant-42:monthly-close:2026-11`; không lấy thời gian hiện tại của mỗi Pod để sinh một kỳ khác nhau khi retry.

### 4.2. Cùng khóa phải tương ứng cùng nội dung

Bên nhận cần lưu cả khóa, nội dung hoặc dấu vân tay của nội dung, và kết quả đã xử lý:

```text
operation_key -> canonical_payload, result
```

Quy tắc xử lý:

1. Chưa có khóa: thực hiện và lưu kết quả trong cùng giao dịch với thay đổi nghiệp vụ.
2. Đã có khóa, cùng nội dung: trả kết quả đã lưu.
3. Đã có khóa, khác nội dung: báo xung đột; không âm thầm nhận một số tiền mới.

Nếu dùng hash, cần chuẩn hóa nội dung trước: thứ tự thuộc tính, đơn vị tiền, cách biểu diễn số, giá trị mặc định và phiên bản schema. Không hash chuỗi JSON tùy ý rồi cho rằng hai chuỗi khác nhau luôn là hai ý định khác nhau.

Khóa duy nhất trong cơ sở dữ liệu là hàng rào cuối chống hai request cùng thấy “chưa tồn tại”. Mẫu `SELECT` rồi ghi ở hai giao dịch rời rạc không cung cấp tính nguyên tử.

### 4.3. Chọn thời gian lưu khóa theo khả năng phát lại

Giữ khóa ít nhất qua toàn bộ khoảng thời gian mà cùng ý định có thể quay lại: retry tự động, message được phát lại, phục hồi backup, đối soát và thao tác thủ công.

Nếu xóa khóa sau một ngày nhưng cho phát lại dữ liệu sau một tháng, lớp chống trùng đã mất tác dụng. Với ràng buộc như “mỗi tenant chỉ có một hóa đơn mang mã này”, nên giữ thêm unique constraint trên chính dữ liệu nghiệp vụ.

Hợp đồng của nhà cung cấp có thể có thời hạn và quy tắc riêng. Chẳng hạn Stripe API v1 cho phép loại khóa sau khi chúng tồn tại ít nhất 24 giờ và kiểm tra sự khớp nhau của tham số. Không suy ra mọi API thanh toán đều có cùng hành vi. [Nguồn: Stripe — Idempotent requests](https://docs.stripe.com/api/idempotent_requests).

## 5. Fencing phải được thực thi ở nơi chấp nhận tác dụng phụ

### 5.1. Epoch biểu diễn một phiên quyền ghi

Fencing token thường là một số thứ tự tăng dần, gọi là epoch:

```text
Phiên A: epoch = 41
Phiên B: epoch = 42
```

Sau khi hệ thống đích đã kích hoạt epoch 42, nó phải từ chối request mang epoch 41, kể cả A vẫn đang chạy.

Hai kiểu kiểm tra thường gặp:

- **Lưu token lớn nhất đã thấy:** từ chối token nhỏ hơn mốc đã lưu; token bằng mốc vẫn có thể hợp lệ cho nhiều lệnh cùng phiên.
- **Kích hoạt một phiên hiện hành:** ghi epoch và holder hiện hành trước, sau đó chỉ nhận request khớp phiên đó.

Bài học dùng kiểu thứ hai. Bước kích hoạt phiên mới và giao dịch ghi nghiệp vụ cùng tranh chấp một hàng trong PostgreSQL, tạo ra thứ tự rõ ràng.

Điểm cắt phải được nói chính xác: fencing chặn phiên cũ **sau khi bước kích hoạt phiên mới tại hệ thống đích đã commit**. Nó không quay ngược một tác dụng phụ đã được chấp nhận trước điểm cắt đó.

### 5.2. Token phải có nguồn cấp có thẩm quyền

Một hệ thống cấp token đúng cần bảo đảm:

1. Quyền ghi được cấp theo một thứ tự nhất quán cho từng phạm vi tài nguyên.
2. Token gắn với đúng lần cấp quyền, không được tái sử dụng cho phiên khác.
3. Phiên cũ không được tự xin một token mới để vượt qua hàng rào.
4. Bên nhận xác minh token và holder dựa trên trạng thái đáng tin cậy.
5. Khôi phục dữ liệu hoặc tạo lại tài nguyên không làm token cũ trở nên hợp lệ.

Không thể sửa một callback bầu leader bằng cách thêm `SELECT nextval(...)` tùy ý rồi coi đó là giao thức fencing hoàn chỉnh. Callback cũ có thể bị trì hoãn, chạy sau callback mới và lấy số lớn hơn. Sequence chỉ cho thứ tự lấy số, chưa chứng minh thứ tự cấp leadership.

Có hai hướng thiết kế thực tế:

- Dùng một coordinator có giao thức cấp quyền kèm token tăng dần và bảo đảm token gắn với lần cấp đó.
- Đưa quyền ghi nghiệp vụ vào cơ sở dữ liệu hoặc một dịch vụ điều phối bền vững; Kubernetes election chọn Pod đề nghị chạy, còn authority này quyết định phiên nào thực sự được ghi.

Nếu chọn hướng thứ hai, cần thừa nhận điểm quyết định quyền ghi nằm ở authority nghiệp vụ. Việc đọc Kubernetes Lease và cập nhật PostgreSQL không tự trở thành một giao dịch phân tán nguyên tử.

Ví dụ trong bài **giả định bước cấp và kích hoạt epoch do một coordinator đáng tin cậy thực hiện**. Các lệnh đổi epoch trong phần thực hành mô phỏng coordinator bằng một phiên quản trị; chúng không phải đoạn mã để mọi Pod tự chạy khi nhận sự kiện.

### 5.3. Những giá trị không nên tự biến thành fencing token

- Pod UID nhận diện Pod nhưng không biểu diễn thứ tự các phiên.
- Đồng hồ máy và timestamp không phải bộ cấp quyền nhất quán.
- `holderIdentity` nhận diện holder, không phải một epoch tăng dần.
- `leaseTransitions` không tự bảo đảm vòng đời token khi Lease bị xóa rồi tạo lại.
- `metadata.resourceVersion` là giá trị opaque theo hợp đồng Kubernetes; không parse thành số để xây giao thức fencing cho dữ liệu ngoài Kubernetes. [Nguồn: Kubernetes ObjectMeta](https://kubernetes.io/docs/reference/kubernetes-api/definitions/object-meta-v1-meta/).

Giá trị chỉ được mang qua header như `X-Fencing-Token` chưa tạo bảo vệ. Bên nhận phải kiểm tra và chấp nhận tác dụng phụ nguyên tử. Với nhiều hệ thống đích, cần biết hệ thống nào thực thi hàng rào nào.

## 6. Ví dụ PostgreSQL: ghi hóa đơn và outbox trong một giao dịch

### 6.1. Phạm vi và giả định

Ví dụ dùng PostgreSQL 17 trở lên, cú pháp tương thích PostgreSQL 17. Mỗi tenant có một scope `invoice:<tenant>`. Tất cả thao tác phát hành hóa đơn của tenant phải qua cùng đường ghi có kiểm tra fence.

Đây là ví dụ có thể chạy trong cơ sở dữ liệu lab. Nó minh họa phần **thực thi** idempotency và fencing; phần cấp quyền production phải đáp ứng hợp đồng ở mục 5.

Các bảng lưu dữ liệu:

```sql
CREATE TABLE billing_writer (
    scope  text PRIMARY KEY,
    epoch  bigint NOT NULL CHECK (epoch > 0),
    holder text NOT NULL
);

CREATE TABLE billing_invoice (
    tenant_id  text NOT NULL,
    invoice_id text NOT NULL,
    amount     numeric(18, 2) NOT NULL CHECK (amount > 0),
    currency   text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    PRIMARY KEY (tenant_id, invoice_id)
);

CREATE TABLE billing_operation (
    scope         text NOT NULL,
    operation_key text NOT NULL,
    payload       jsonb NOT NULL,
    result        jsonb NOT NULL,
    PRIMARY KEY (scope, operation_key)
);

CREATE TABLE billing_outbox (
    event_id      text PRIMARY KEY,
    scope         text NOT NULL,
    operation_key text NOT NULL,
    payload       jsonb NOT NULL,
    state         text NOT NULL DEFAULT 'PENDING'
                  CHECK (state IN ('PENDING', 'SENDING', 'SENT', 'UNKNOWN')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (scope, operation_key)
);
```

Hàng `billing_writer` không được tạo tự động trong đường xử lý request. Thiếu hàng, sai holder hoặc sai epoch đều phải dừng ghi.

Trong lab, coordinator cấp phiên đầu tiên:

```sql
INSERT INTO billing_writer (scope, epoch, holder)
VALUES ('invoice:tenant-42', 41, 'pod-a-session-1');
```

### 6.2. Hàm ghi nguyên tử

Hàm dưới đây tạo khóa từ định danh nghiệp vụ, so khớp nội dung khi retry, ghi hóa đơn và ghi sự kiện outbox. Nó không gọi HTTP.

```sql
CREATE OR REPLACE FUNCTION record_invoice(
    p_epoch      bigint,
    p_holder     text,
    p_tenant     text,
    p_invoice    text,
    p_amount     numeric,
    p_currency   text
) RETURNS jsonb
LANGUAGE plpgsql
AS $$
DECLARE
    v_scope   text;
    v_key     text;
    v_payload jsonb;
    v_result  jsonb;
    v_writer  billing_writer%ROWTYPE;
    v_old     billing_operation%ROWTYPE;
BEGIN
    IF p_epoch IS NULL OR p_epoch <= 0
       OR p_holder IS NULL OR p_holder = ''
       OR p_tenant IS NULL OR p_tenant !~ '^[A-Za-z0-9_-]+$'
       OR p_invoice IS NULL OR p_invoice !~ '^[A-Za-z0-9_-]+$'
       OR p_amount IS NULL OR p_amount <= 0
       OR p_amount <> round(p_amount, 2)
       OR p_currency IS NULL OR p_currency !~ '^[A-Z]{3}$' THEN
        RAISE EXCEPTION 'INVALID_COMMAND';
    END IF;

    v_scope := 'invoice:' || p_tenant;
    v_key := 'issue-invoice:v1:' || p_tenant || ':' || p_invoice;
    v_payload := jsonb_build_object(
        'version', 1,
        'tenantId', p_tenant,
        'invoiceId', p_invoice,
        'amount', p_amount,
        'currency', p_currency
    );

    SELECT * INTO v_writer
    FROM billing_writer
    WHERE scope = v_scope
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'MISSING_FENCE';
    END IF;

    IF v_writer.epoch <> p_epoch OR v_writer.holder <> p_holder THEN
        RAISE EXCEPTION 'STALE_WRITER';
    END IF;

    SELECT * INTO v_old
    FROM billing_operation
    WHERE scope = v_scope AND operation_key = v_key;

    IF FOUND THEN
        IF v_old.payload IS DISTINCT FROM v_payload THEN
            RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT';
        END IF;
        RETURN v_old.result;
    END IF;

    INSERT INTO billing_invoice (
        tenant_id, invoice_id, amount, currency
    ) VALUES (
        p_tenant, p_invoice, p_amount, p_currency
    );

    v_result := jsonb_build_object(
        'status', 'RECORDED',
        'invoiceId', p_invoice,
        'operationKey', v_key
    );

    INSERT INTO billing_operation (
        scope, operation_key, payload, result
    ) VALUES (
        v_scope, v_key, v_payload, v_result
    );

    INSERT INTO billing_outbox (
        event_id, scope, operation_key, payload
    ) VALUES (
        v_key, v_scope, v_key, v_payload
    );

    RETURN v_result;
END;
$$;
```

`RECORDED` nghĩa là ý định đã được ghi bền vững, chưa đồng nghĩa nhà cung cấp đã phát hành hóa đơn. Tên trạng thái cần phản ánh đúng ranh giới này.

Khóa hàng `FOR UPDATE` giữ bước đổi epoch và bước ghi nghiệp vụ theo một thứ tự. PostgreSQL giữ khóa hàng đến khi giao dịch kết thúc. Không tách việc đọc fence sang một giao dịch khác rồi mới ghi hóa đơn. [Nguồn: PostgreSQL 17 — Explicit Locking](https://www.postgresql.org/docs/17/explicit-locking.html).

Vì mọi request trong cùng scope đều khóa hàng fence trước, hai request đồng thời cho cùng tenant được xử lý tuần tự ở phần này. Primary key của hóa đơn và operation vẫn cần giữ để bảo vệ bất biến nghiệp vụ. Đổi scope thành từng partition có thể tăng thông lượng, nhưng phạm vi cấp token, phạm vi khóa và mọi đường ghi phải được thay đổi đồng bộ.

Tất cả exception trong hàm phải làm giao dịch gọi thất bại. Không bắt lỗi rồi commit phần ghi trước đó. Với tenant có lưu lượng lớn, cần đo thời gian giữ khóa, giới hạn thời gian giao dịch và dùng thứ tự khóa nhất quán khi một thao tác đụng nhiều scope.

### 6.3. Kích hoạt phiên kế tiếp

Giả sử coordinator đã cấp phiên 42 cho B. Phiên điều phối tin cậy thực hiện:

```sql
BEGIN;

UPDATE billing_writer
SET epoch = 42, holder = 'pod-b-session-1'
WHERE scope = 'invoice:tenant-42'
  AND epoch = 41
  AND holder = 'pod-a-session-1';

-- Phải xác nhận đúng một hàng được cập nhật.
-- Nếu bằng 0: ROLLBACK và đọc lại trạng thái; không ép ghi đè.
COMMIT;
```

Ở production, API của coordinator phải kiểm tra số hàng cập nhật và commit trước khi cho B chạy. Chỉ coordinator được sửa epoch và holder; worker không được quyền tự nâng epoch hay lấy một token hiện tại rồi mạo nhận phiên mới.

Hai trường hợp cạnh tranh có kết quả rõ ràng:

- A đã khóa hàng trước: giao dịch ngắn của A có thể commit; bước kích hoạt B chờ và commit sau.
- B kích hoạt và commit trước: A đọc phiên 42 rồi thất bại với `STALE_WRITER`.

Như vậy, giao dịch cũ đã được sắp trước điểm cắt có thể hoàn tất. Sau điểm cắt, giao dịch của phiên cũ không được chấp nhận. Không có cam kết rằng mọi câu lệnh của A dừng đúng thời điểm B được Kubernetes bầu.

Trong lab, cùng người học có thể dùng quyền quản trị để tạo bảng và đổi phiên. Trong production, đường ghi nên được đóng gói và phân quyền để không có tài khoản ứng dụng bỏ qua kiểm tra. Tham số `p_holder` là dữ liệu kiểm tra, không phải cơ chế xác thực caller.

### 6.4. Gọi từ Spring

Một Spring service có thể gọi hàm qua JDBC trong giao dịch:

```java
@Service
public class InvoiceWriter {
    private final JdbcTemplate jdbc;

    public InvoiceWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public String record(
            long epoch, String holder,
            String tenantId, String invoiceId,
            BigDecimal amount, String currency) {
        return jdbc.queryForObject(
            "select record_invoice(?, ?, ?, ?, ?, ?)::text",
            String.class,
            epoch, holder, tenantId, invoiceId, amount, currency
        );
    }
}
```

Ví dụ cần Spring JDBC, transaction manager và PostgreSQL driver được cấu hình. Các annotation và kiểu được import từ Spring và Java tương ứng. Gọi service qua Spring bean để cơ chế giao dịch có hiệu lực; không dựa vào self-invocation để mở giao dịch mới.

Một task đã tạo phải giữ **snapshot bất biến của phiên**: scope, epoch và holder. Nếu task của A đang chạy dở rồi đọc epoch mới từ biến toàn cục, nó có thể mang token của phiên mới cho công việc cũ. Khi cần tiếp tục công việc, phiên mới phải đọc lại dữ liệu bền vững và quyết định retry bằng cùng khóa nghiệp vụ.

## 7. Tích hợp với vòng đời leader của Spring Cloud Kubernetes

Ở nhánh Spring Cloud Kubernetes 3.3 với cơ chế Fabric8 dựa trên ConfigMap, ứng dụng nhận `OnGrantedEvent` và `OnRevokedEvent`. Nhánh triển khai khác có thể dùng kiểu sự kiện và tài nguyên khóa khác; cần chọn đúng tài liệu theo dependency của dự án. [Nguồn: Spring Cloud Kubernetes 3.3 — Leader Election](https://docs.spring.io/spring-cloud-kubernetes/reference/3.3/leader-election.html).

Luồng tích hợp ở mức thiết kế:

```text
Được cấp leadership
  -> tạo generation cục bộ cho lần cấp này
  -> đề nghị coordinator cấp/kích hoạt phiên ghi
  -> xác nhận activation đã commit và generation chưa bị thu hồi
  -> chạy scheduler bằng snapshot phiên đó

Bị thu hồi leadership
  -> đánh dấu generation cũ không còn hoạt động
  -> dừng nhận công việc mới
  -> hủy scheduler và yêu cầu task đang chạy dừng
  -> giữ fencing và idempotency ở bên nhận làm hàng rào cuối
```

Đây là giả mã kiến trúc, không phải các API có sẵn của Spring Cloud Kubernetes. Đặc biệt, coordinator không được triển khai bằng callback gọi sequence tùy ý như đã cảnh báo ở mục 5.

Nếu activation đang diễn ra mà revoke đến trước khi activation trả về, kết quả activation muộn không được tự khởi động lại scheduler của generation đã thu hồi. Nếu cần hoàn trả phiên đã cấp, chỉ thu hồi đúng epoch/holder đó; không xóa nhầm phiên kế tiếp.

Hủy `Future`, interrupt thread hoặc đặt cờ dừng giúp giảm công việc thừa, nhưng không bảo đảm rollback HTTP request đã được hệ thống khác nhận. Shutdown nên có thời hạn; giao dịch và từng request cũng phải có timeout phù hợp.

Nếu PostgreSQL không truy cập được hoặc coordinator không xác nhận được phiên, dừng phát tác dụng phụ mới. Không dùng token cache như lối bỏ qua kiểm tra. Lỗi tạm thời có thể retry theo chính sách, nhưng `STALE_WRITER` phải dừng phiên cũ và quay lại luồng điều phối.

## 8. Outbox bảo vệ ý định, bên nhận bảo vệ tác dụng phụ

### 8.1. Khoảng trống khi vừa ghi DB vừa gọi HTTP

Hai thứ tự ngây thơ đều có cửa sổ lỗi:

```text
Gọi nhà cung cấp thành công -> Pod chết -> chưa ghi DB
Ghi DB thành công -> Pod chết -> chưa gọi nhà cung cấp
```

Giữ giao dịch PostgreSQL mở trong lúc gọi HTTP không làm nhà cung cấp trở thành thành viên của giao dịch đó. Cách này còn kéo dài thời gian giữ khóa fence và cản handover.

Trong ví dụ, hóa đơn, operation và outbox cùng commit. Một dispatcher đọc outbox để gửi đi sau. Dispatcher có thể là nhóm worker riêng; không nhất thiết cần leader nếu cơ chế claim và retry đã đúng.

### 8.2. Dùng cùng khóa ở hệ thống đích

Request minh họa cho một API có hỗ trợ khóa lũy đẳng:

```http
POST /invoices
Idempotency-Key: issue-invoice:v1:tenant-42:INV-001
Content-Type: application/json

{"tenantId":"tenant-42","invoiceId":"INV-001","amount":125000,"currency":"VND"}
```

Tên endpoint và header trong ví dụ là hợp đồng giả định. Chỉ áp dụng khi API đích thực sự hỗ trợ và có tài liệu rõ ràng.

Luồng dispatcher cần xử lý ít nhất:

1. Claim bản ghi bằng cơ chế nguyên tử, có thời hạn hoặc khả năng phục hồi khi worker chết.
2. Gửi payload đã lưu, giữ nguyên `event_id` và khóa nghiệp vụ qua mọi lần thử.
3. Thành công được xác nhận: đánh dấu `SENT`.
4. Timeout sau khi gửi: coi kết quả có thể đã xảy ra; lưu trạng thái cần kiểm tra hoặc retry theo hợp đồng idempotency.
5. Worker chết sau khi đích thành công nhưng trước khi lưu `SENT`: lần xử lý sau vẫn dùng cùng khóa.

Các trạng thái `SENDING` và `UNKNOWN` trong schema giúp biểu diễn vòng đời, nhưng chỉ thêm cột trạng thái chưa tạo được cơ chế claim an toàn. Cần thiết kế riêng owner của lần claim, thời hạn claim và cập nhật có điều kiện để lần xử lý cũ không ghi đè kết quả của lần mới.

Nếu bên nhận là dịch vụ nội bộ, có thể lưu inbox với unique key trên `event_id`, và commit inbox cùng thay đổi nghiệp vụ. Cờ “đã nhận message” trong RAM không sống qua restart.

### 8.3. Khi cần fencing cho HTTP

Idempotency ở nhà cung cấp ngăn phát hành trùng cùng hóa đơn; nó không tự chặn một hóa đơn khác do leader cũ tạo.

Có hai cách đặt ranh giới:

- Mọi ý định được chấp nhận qua giao dịch fenced trong DB; dispatcher chỉ phát những ý định đã commit. Khi ấy một ý định hợp lệ trước handover có thể được gửi sau handover.
- API đích cũng kiểm tra phiên hoặc version nguyên tử nếu nghiệp vụ yêu cầu từ chối lệnh cũ tại chính thời điểm thực hiện ở đích.

Không gửi epoch của producer cũ rồi mặc định mọi outbox cũ đều phải hủy. Một outbox đã commit có thể là công việc hợp lệ cần hoàn tất. Nếu nghiệp vụ thật sự muốn thu hồi ý định cũ, phải có trạng thái hủy/version và quy tắc kiểm tra ở nơi thực hiện.

Khi nhà cung cấp không hỗ trợ idempotency hoặc truy vấn theo mã tham chiếu, không thể kết luận timeout là thất bại và gửi lại vô điều kiện. Đưa vào trạng thái chưa xác định, đối soát, hoặc can thiệp theo quy trình nghiệp vụ. Fencing tại DB không thu hồi được tác dụng phụ đã xảy ra ở nhà cung cấp.

## 9. Thực hành lỗi và kết quả cần quan sát

Các thao tác dưới đây dành cho cơ sở dữ liệu lab đã tạo schema và hàm ở mục 6. Mỗi trường hợp lỗi nên chạy trong giao dịch riêng; sau exception, rollback trước khi chạy trường hợp tiếp theo.

### 9.1. Gửi lại cùng một ý định

Trong phiên A, gọi hai lần cùng lệnh:

```sql
SELECT record_invoice(
    41, 'pod-a-session-1',
    'tenant-42', 'INV-001', 125000, 'VND'
);

SELECT record_invoice(
    41, 'pod-a-session-1',
    'tenant-42', 'INV-001', 125000, 'VND'
);

SELECT count(*) FROM billing_invoice
WHERE tenant_id = 'tenant-42' AND invoice_id = 'INV-001';

SELECT count(*) FROM billing_outbox
WHERE event_id = 'issue-invoice:v1:tenant-42:INV-001';
```

Kỳ vọng: hai lời gọi trả cùng kết quả, mỗi truy vấn đếm trả `1`. Nếu cùng khóa nhưng đổi số tiền thành `126000`, phải nhận `IDEMPOTENCY_CONFLICT` và không có thêm hóa đơn hay outbox.

### 9.2. Leader cũ gửi lệnh mới

Chạy bước kích hoạt epoch 42 ở mục 6.3, rồi thử:

```sql
-- A đã cũ, kể cả đây là một invoice hoàn toàn mới.
SELECT record_invoice(
    41, 'pod-a-session-1',
    'tenant-42', 'INV-002', 200000, 'VND'
);
-- Kỳ vọng: STALE_WRITER.

SELECT record_invoice(
    42, 'pod-b-session-1',
    'tenant-42', 'INV-002', 200000, 'VND'
);
-- Kỳ vọng: RECORDED.
```

B có thể retry `INV-001` với cùng payload để nhận kết quả A đã commit. A dùng epoch 41 retry `INV-001` vẫn bị từ chối vì hàm kiểm tra fence trước. Đó là lựa chọn giao thức ở đây: chỉ phiên hợp lệ được gọi đường ghi; nếu cần tra cứu kết quả cũ, cung cấp API đọc riêng có xác thực.

### 9.3. Quan sát cạnh tranh bằng hai phiên DB

Ở phiên thứ nhất, dùng phiên B đang hợp lệ:

```sql
BEGIN;
SELECT record_invoice(
    42, 'pod-b-session-1',
    'tenant-42', 'INV-003', 300000, 'VND'
);
-- Tạm thời chưa COMMIT.
```

Ở phiên thứ hai, mô phỏng coordinator kích hoạt phiên 43:

```sql
BEGIN;
UPDATE billing_writer
SET epoch = 43, holder = 'pod-c-session-1'
WHERE scope = 'invoice:tenant-42'
  AND epoch = 42
  AND holder = 'pod-b-session-1';
-- Câu UPDATE chờ phiên thứ nhất kết thúc.
```

Commit phiên thứ nhất, kiểm tra phiên thứ hai cập nhật đúng một hàng rồi commit. Sau đó lệnh ghi mới từ epoch 42 phải thất bại. Thí nghiệm cho thấy điểm cắt nằm ở giao dịch activation, không nằm ở một cờ leader trong JVM.

### 9.4. Những lỗi cần đưa vào kiểm thử hệ thống

| Kịch bản | Bất biến cần kiểm tra |
| --- | --- |
| Dừng Pod sau commit nhưng trước khi trả response | Retry không tạo thêm hóa đơn hoặc outbox |
| Hai request cùng khóa chạy đồng thời | Chỉ một kết quả nghiệp vụ được tạo |
| Thu hồi leadership trong lúc task đang chờ | Task cũ không mượn token mới; bên nhận chặn sau activation |
| Mất API server nhưng DB vẫn hoạt động | Phiên cũ không ghi qua được fence đã chuyển |
| Dispatcher chết sau khi đích nhận request | Phát lại dùng cùng khóa; không tự kết luận tác dụng phụ chưa xảy ra |
| Khôi phục DB hoặc xóa/tạo lại tài nguyên election | Không hồi sinh token cũ; có quy trình vô hiệu hóa worker và request cũ |
| Hết thời gian lưu khóa của nhà cung cấp | Đối soát trước khi phát lại ngoài thời hạn bảo vệ |

Không chỉ kiểm tra log “B đã thành leader”. Bằng chứng quan trọng là số bản ghi, kết quả bên nhận, thao tác bị từ chối và việc phục hồi từ trạng thái chưa xác định.

## 10. Vận hành cùng ConfigMap, Secret, RBAC và health

Cấu hình retry, kích thước batch và timeout có thể đến từ ConfigMap; thông tin kết nối có thể đến từ Secret. Khi dùng Configuration Watcher hoặc cơ chế refresh, không reset epoch bền vững và không sinh lại khóa idempotency của các ý định đã tồn tại.

RBAC cho phép ứng dụng truy cập tài nguyên election cần thiết; nó không thay thế quyền ghi ở PostgreSQL hay xác thực tới API đích. Chọn quyền theo đúng implementation dùng ConfigMap hay Lease, namespace và phạm vi tài nguyên. Tài khoản cập nhật fence, tài khoản ghi nghiệp vụ và dispatcher cần được phân quyền phù hợp với vai trò thực tế.

Theo dõi các tín hiệu:

- Số lần đổi leader và thời gian từ election tới activation.
- Số request bị từ chối vì stale writer.
- Số lần dùng lại kết quả idempotency và xung đột payload.
- Thời gian chờ hàng fence, timeout giao dịch và deadlock.
- Độ trễ outbox, số ý định chưa xác định và thời gian đối soát.

Log có thể mang scope, epoch, định danh phiên và operation key để điều tra. Tránh gắn invoice ID hay operation key vào nhãn metric có số lượng giá trị không giới hạn. Không ghi Secret, thông tin xác thực hoặc payload nhạy cảm vào log.

Follower vẫn có thể khỏe và phục vụ HTTP. Không đánh liveness thất bại chỉ vì một Pod chưa phải leader; điều đó có thể tạo vòng restart vô ích. Readiness quyết định khả năng nhận traffic theo vai trò phục vụ, không chứng minh một task nền được quyền ghi. Một endpoint báo “leader=true” cũng không thay cho kết quả kiểm tra fence tại đích.

Chỉ bật những tính năng Spring Cloud Kubernetes thật sự cần. Nếu bài toán được giải bằng hàng đợi và consumer có idempotency, có thể không cần leader cho dispatcher. Nếu dịch vụ gọi nhau qua Kubernetes Service DNS, việc thêm DiscoveryClient hoặc Spring Cloud LoadBalancer không tạo thêm bảo đảm chống trùng cho thao tác ghi.

## 11. Tiêu chí đánh giá một thiết kế hoàn chỉnh

Trước khi dùng cho tác dụng phụ quan trọng, cần trả lời được:

1. Ý định nghiệp vụ được định danh thế nào và có giữ nguyên qua đổi Pod, retry, replay không?
2. Thành phần nào cấp epoch, tại sao callback cũ không thể lấy quyền mới?
3. Bên nhận kiểm tra quyền và ghi tác dụng phụ trong cùng ranh giới nguyên tử ở đâu?
4. Điểm cắt chuyển phiên nằm ở bước commit nào?
5. Nếu request đã đến nhà cung cấp nhưng response mất, hệ thống phục hồi thế nào?
6. Hết thời hạn idempotency hoặc khôi phục backup có làm mất bảo đảm không?
7. Đường ghi nào có thể bỏ qua fence, unique constraint hoặc inbox?

Đích đến là một hệ thống có thứ tự cấp quyền rõ ràng, nhận diện được cùng ý định nghiệp vụ và phục hồi được sau kết quả chưa xác định. Bầu leader giảm số bên điều phối; idempotency, fencing và giao dịch mới bảo vệ các thay đổi mà người dùng thực sự quan tâm.
