# Điều kiện quay lui khi dữ liệu đã được phiên bản mới ghi

Một kế hoạch nâng cấp Java/JDK hoặc triển khai phiên bản ứng dụng thường có câu “nếu phát sinh lỗi thì rollback về bản cũ”. Câu đó chỉ đúng khi **phiên bản cũ vẫn hiểu và xử lý an toàn mọi dữ liệu, thông điệp và trạng thái mà phiên bản mới đã tạo ra**. Nếu phiên bản mới đã ghi một trạng thái enum chưa từng có, dùng định dạng serialization mới, thay đổi ý nghĩa một cột hoặc phát sự kiện mà consumer cũ không nhận diện, việc đưa JAR hoặc container image cũ trở lại có thể khiến sự cố nghiêm trọng hơn.

**Rollback code không đồng nghĩa rollback dữ liệu.** Thay artifact của ứng dụng thường chỉ thay chương trình đang thực thi. Database, event log, object storage, cache, thông điệp đang chờ xử lý, checkpoint và tác dụng phụ ở hệ thống bên ngoài vẫn giữ trạng thái do phiên bản mới tạo ra. Muốn quay lui an toàn cần kiểm soát cả những trạng thái này.

Bài học trình bày các điều kiện để phiên bản N-1 chạy lại sau khi phiên bản N đã ghi dữ liệu, cách nhận diện thay đổi không thể quay lui, quy trình kiểm thử chéo phiên bản, chiến lược triển khai từng giai đoạn và runbook xử lý khi rollback không còn an toàn.

## 1. Làm rõ ý nghĩa của “quay lui”

Một hệ thống Java thường có nhiều lớp có vòng đời độc lập:

~~~text
Application image / JAR         Có thể đổi N -> N-1
         |
         v
Database schema                 Có thể đã được migrate
         |
         v
Database records                Có thể đã có dữ liệu kiểu mới
         |
         v
Event stream / message queue    Có thể đã phát event format mới
         |
         v
Cache / object storage          Có thể đã lưu serialization mới
         |
         v
External systems                Có thể đã nhận giao dịch / side effect
~~~

Khi đặt câu hỏi “có rollback được không?”, phải chỉ rõ **đối tượng nào được quay lui**:

- **Rollback ứng dụng:** chạy lại binary/config của N-1; không tự động đổi dữ liệu.
- **Rollback schema:** đảo một hoặc nhiều thay đổi database schema, nếu migration thực sự đảo được.
- **Rollback dữ liệu:** đưa bản ghi về trạng thái tương thích với N-1 bằng chuyển đổi, phục hồi backup hoặc thao tác bù.
- **Rollback giao thức:** thay đổi producer/consumer trở lại định dạng thông điệp mà các phiên bản cũ hiểu.
- **Rollback quy trình nghiệp vụ:** bù trừ hoặc đảo những tác dụng phụ đã xảy ra bên ngoài như gửi email, thanh toán hoặc cập nhật hệ thống khác.

Những loại rollback này không thể gộp thành một lệnh triển khai. Ví dụ, một database đã có dòng mới ở phiên bản N có thể không cần rollback schema, nhưng N-1 vẫn không đọc được giá trị trạng thái vừa ghi. Ngược lại, N-1 có thể đọc dữ liệu mới nhưng ghi lại bản ghi theo logic cũ và xóa mất thông tin mới.

### 1.1. Bốn dạng tương thích cần phân biệt

| Loại | Câu hỏi | Ví dụ lỗi |
|---|---|---|
| Tương thích nhị phân | Binary N-1 có chạy được trên JDK/dependency đã triển khai không? | `UnsupportedClassVersionError`, `NoSuchMethodError`. |
| Tương thích schema | N-1 có kết nối và thao tác được với schema hiện tại không? | Cột bị đổi tên, constraint mới từ chối câu lệnh cũ. |
| Tương thích dữ liệu/hành vi | N-1 có hiểu giá trị và ý nghĩa của các record do N ghi không? | Enum mới không được nhận diện, đơn vị tiền thay đổi. |
| Tương thích giao thức | N-1 có đọc/ghi được message, event và cache format do N tạo không? | JSON/Protobuf/Java serialization không tương thích. |

Nâng JDK còn có thể đổi hành vi xử lý thời gian, charset, locale, Unicode, serialization hoặc thư viện bảo mật. Những thay đổi đó cần được tính vào rollback ngay cả khi application schema trên giấy không đổi.

## 2. Điều kiện cốt lõi: N-1 phải xử lý an toàn dữ liệu do N tạo

Giả sử hai phiên bản ứng dụng là:

- **N-1:** bản hiện hành, có khả năng được triển khai lại khi xảy ra sự cố.
- **N:** bản được thử nghiệm hoặc vừa phát hành.

Đặt `D_N` là tập trạng thái dữ liệu có thể được N ghi trong khoảng rollout. Muốn **rollback chỉ bằng code** từ N về N-1 mà không sửa dữ liệu, cần có ít nhất những bảo đảm sau:

1. **Đọc được:** N-1 có thể đọc và parse mọi trạng thái thuộc `D_N` mà không lỗi.
2. **Hiểu đúng:** N-1 diễn giải dữ liệu theo nghĩa nghiệp vụ tương thích, không chỉ bỏ qua field lỗi.
3. **Xử lý được:** N-1 vẫn thực hiện được các luồng nghiệp vụ bắt buộc với dữ liệu đó.
4. **Ghi lại an toàn:** nếu N-1 cập nhật bản ghi do N tạo, nó không âm thầm xóa, chuyển sai hoặc phá hỏng dữ liệu mà N đã thêm.
5. **Không phá invariant:** những ràng buộc về số tiền, trạng thái, tính duy nhất, tham chiếu và phân quyền vẫn được duy trì.
6. **Có thể xử lý tác dụng phụ:** event, queue, checkpoint, cache và tương tác với dịch vụ khác vẫn vận hành với binary cũ.
7. **Môi trường còn chạy được:** N-1 vẫn tương thích với JDK, cấu hình, thư viện, database driver và hạ tầng còn tồn tại sau rollout.

Đây là điều kiện **cần đánh giá** đối với rollback code-only. Nó không bảo đảm mọi chức năng tự động hoạt động hoàn hảo; nhóm phải kiểm thử những đường nghiệp vụ và trạng thái có thể xảy ra.

### 2.1. “Đọc được” không có nghĩa “an toàn”

Giả sử N thêm field `fraudReviewReason` vào JSON của một đơn hàng. N-1 được cấu hình bỏ qua unknown fields nên không ném exception. Nhìn bên ngoài, N-1 “đọc được”.

Nhưng nếu N-1 deserializes JSON thành DTO cũ rồi serializes lại toàn bộ object khi cập nhật địa chỉ giao hàng, field `fraudReviewReason` có thể bị mất. Rollback có thể thành công lúc startup nhưng gây **mất dữ liệu âm thầm** khi người dùng sửa đơn hàng.

Vì vậy, phải kiểm tra **read–modify–write round trip**, không chỉ parse một chiều.

### 2.2. “Không ném exception” cũng chưa đủ

Giả sử N thêm trạng thái:

~~~text
PENDING_FRAUD_REVIEW
~~~

N-1 không có trạng thái này nhưng có nhánh mặc định “mọi trạng thái lạ là APPROVED”. Nó không crash, nhưng có thể cho phép thực hiện giao dịch chưa được kiểm duyệt.

Đây là lỗi nghiệp vụ/bảo mật nghiêm trọng hơn một lỗi parse rõ ràng. **Fail closed** đối với trạng thái chưa hiểu thường an toàn hơn diễn giải thành trạng thái cho phép.

### 2.3. Hai câu hỏi phải trả lời trước rollout

- *Bản N có tạo ra trạng thái mới nào mà N-1 chưa từng thấy không?*
- *Nếu N-1 nhìn thấy và sau đó ghi lại trạng thái đó, điều gì sẽ xảy ra?*

Nếu chưa trả lời được hai câu hỏi này bằng test và bằng chứng, chưa thể tuyên bố “rollback an toàn”.

## 3. Những thay đổi dữ liệu thường chặn rollback

### 3.1. Giá trị enum mới

Phiên bản cũ:

~~~java
enum OrderStatus {
    CREATED, PAID, SHIPPED, CANCELLED
}
~~~

Phiên bản mới:

~~~java
enum OrderStatus {
    CREATED, PAID, PENDING_FRAUD_REVIEW,
    SHIPPED, CANCELLED
}
~~~

Nếu database lưu trạng thái dưới dạng chuỗi và N ghi `PENDING_FRAUD_REVIEW`, code cũ có thể lỗi:

~~~java
OrderStatus status =
    OrderStatus.valueOf(dbValue);
~~~

Khi `dbValue` là tên mới, `valueOf` ném `IllegalArgumentException`. Nếu JSON được ánh xạ trực tiếp sang enum, thư viện deserialization cũng có thể báo lỗi khi gặp giá trị chưa biết.

Giải pháp phải được chuẩn bị **trước khi N được phép ghi trạng thái mới**: triển khai N-1+ một phiên bản tương thích với giá trị chưa biết và xử lý an toàn, hoặc khóa khả năng tạo trạng thái mới bằng feature flag cho đến khi cửa sổ rollback đóng. Không thể sửa N-1 đã phát hành bằng cách chỉ thay đổi config của N.

### 3.2. Thêm field mới với ý nghĩa bắt buộc

Ví dụ N thêm `currency` và cho phép thanh toán bằng nhiều đồng tiền. Trước đó, N-1 ngầm hiểu mọi số tiền là VND. Nếu N ghi:

~~~json
{
  "orderId": "O-100",
  "amount": 125,
  "currency": "USD"
}
~~~

N-1 có thể parse `amount=125` mà không biết đơn vị USD và xử lý như 125 VND. Đây là **không tương thích ngữ nghĩa**, dù JSON có thể đọc thành công.

Để rollback, không thể chỉ thêm lại một field mặc định. Phải đảm bảo phiên bản cũ không nhận những record có currency mà nó không hiểu, hoặc đã được nâng để xử lý đa tiền tệ trước khi N ghi.

### 3.3. Đổi đơn vị hoặc cách mã hóa

Thay đổi từ `amountCents` sang `amountDecimal` có thể yêu cầu chuyển đổi dữ liệu; thay từ thời gian Unix milliseconds sang microseconds có thể làm code cũ tính thời gian sai dù kiểu dữ liệu vẫn là `long`.

Những thay đổi “cùng kiểu nhưng khác nghĩa” đặc biệt nguy hiểm vì không phải lúc nào có lỗi compile/parse để cảnh báo.

### 3.4. Đổi tên/xóa cột hoặc field

Nếu N xóa cột `customer_name` sau khi chuyển dữ liệu sang `given_name` và `family_name`, N-1 có thể thất bại vì SQL vẫn truy cập `customer_name`.

Thậm chí nếu schema giữ cột cũ nhưng N ngừng cập nhật nó, N-1 có thể đọc dữ liệu thiếu hoặc đã lỗi thời. Giữ tên cột **chưa đủ**, còn phải giữ nghĩa và tính nhất quán.

### 3.5. Ràng buộc database mới

N có thể áp dụng `NOT NULL`, foreign key, unique index, enum type hoặc CHECK constraint mới. Khi N-1 rollback, một câu lệnh INSERT/UPDATE trước đây hợp lệ có thể bị từ chối.

Một ví dụ:

~~~sql
-- Schema cũ cho phép ghi order mà chưa có review_state.
ALTER TABLE orders
  ADD COLUMN review_state VARCHAR(30);

-- Nếu sau đó ép NOT NULL mà N-1 không ghi cột này:
ALTER TABLE orders
  ALTER COLUMN review_state SET NOT NULL;
~~~

Trên hệ CSDL hỗ trợ cú pháp này (ví dụ PostgreSQL), câu lệnh cuối có thể làm INSERT của N-1 thất bại nếu nó không cung cấp `review_state` và cột không có default phù hợp.

Không nên thực hiện bước *contract* trước khi mọi binary có thể được rollback đã hỗ trợ schema mới.

### 3.6. Serialization format và version

Java native serialization, JSON, Avro, Protobuf, CBOR, Kryo, cache binary hoặc cấu trúc riêng có các quy tắc tương thích khác nhau. Một bản N ghi dữ liệu mới mà N-1 không deserialize được có thể làm cache, queue hoặc database blob trở thành “điểm nổ” sau rollback.

Với Java serialization, `serialVersionUID` và thay đổi class structure có thể ảnh hưởng tới compatibility; giữ `serialVersionUID` không tự bảo đảm mọi thay đổi đều an toàn. Với Protobuf, việc thêm field mới có thể phù hợp nếu quản lý field numbers, wire types và unknown fields đúng cách, nhưng đổi nghĩa một field hoặc tái sử dụng số field cũ là rủi ro lớn. Nếu qua trung gian JSON hoặc thư viện chuyển đổi, unknown fields có thể bị mất khi ghi lại.

### 3.7. Event version và trạng thái tiêu thụ

Nếu N phát sự kiện mới vào Kafka hoặc một message broker mà N-1 không hiểu, rollback producer/consumer không tự xóa những event đã phát.

N-1 có thể:
- Fail liên tục khi đọc một event mới.
- Gửi message vào dead-letter queue.
- Bỏ qua dữ liệu quan trọng khiến trạng thái downstream lệch.
- Ghi offset/checkpoint không đúng.
- Reprocess event, gây giao dịch trùng nếu consumer không idempotent.

Vì vậy, event compatibility là một điều kiện rollback độc lập với schema của database chính.

## 4. Ví dụ xuyên suốt: đơn hàng có bước duyệt rủi ro

Giả sử hệ thống đơn hàng có một dịch vụ Java, database `orders`, queue phát sự kiện và một worker xử lý thanh toán.

### 4.1. Ở phiên bản N-1

~~~text
CREATED --> PAID --> SHIPPED
    |
    +--> CANCELLED
~~~

Schema minh họa:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(40) NOT NULL,
    amount_minor BIGINT NOT NULL
);
~~~

Ứng dụng N-1 chỉ hiểu bốn trạng thái. Worker xử lý thanh toán khi nhận event `OrderPaid`.

### 4.2. Phiên bản N thêm trạng thái chờ duyệt

N muốn bổ sung một trạng thái mới:

~~~text
CREATED --> PENDING_FRAUD_REVIEW --> PAID
                                 |
                                 +--> CANCELLED
~~~

N có thể ghi:

~~~sql
UPDATE orders
SET status = 'PENDING_FRAUD_REVIEW'
WHERE id = 1234;
~~~

N cũng phát event:

~~~json
{
  "eventType": "OrderReviewRequired",
  "version": 2,
  "orderId": 1234,
  "reviewReason": "RISK_SCORE_HIGH"
}
~~~

Bây giờ giả sử N gặp một regression liên quan đến JDK mới, operator triển khai lại N-1 ngay lập tức. N-1 có thể:

- Không parse được `status` mới.
- Đi vào nhánh `default` không phù hợp.
- Không xử lý được event `OrderReviewRequired` đã nằm trong queue.
- Ghi lại đơn hàng và vô tình làm mất dữ liệu review.
- Cho phép xử lý thanh toán trong khi lẽ ra phải chờ duyệt.

**Quay lui N-1 không thể được xem là an toàn** chỉ vì JAR cũ vẫn khởi động trên JDK hiện tại.

### 4.3. Ba hướng xử lý khả thi

**Hướng A – chặn ghi trạng thái mới trong cửa sổ rollback.** Triển khai code N nhưng giữ feature flag tạo `PENDING_FRAUD_REVIEW` ở trạng thái tắt. Khi cần rollback, toàn bộ dữ liệu vẫn ở tập trạng thái N-1 hiểu. Cần test mọi đường ghi, gồm API, batch, scheduler và consumer.

**Hướng B – chuẩn bị N-1 thành bản rollback-compatible trước.** Một phiên bản chuyển tiếp N-1+ được phát hành để hiểu và xử lý an toàn trạng thái review, dù chưa bật chức năng mới. Khi đó rollback từ N về N-1+ có thể an toàn hơn rollback về bản N-1 nguyên thủy.

**Hướng C – xây dựng bước data remediation trước khi rollback.** Nếu trạng thái mới đã được ghi, cần xác định liệu có thể chuyển đổi mỗi record về trạng thái cũ mà không mất nghĩa hay vi phạm quy trình. Nếu không có ánh xạ an toàn, cần giữ ứng dụng mới hoặc một bản hotfix có khả năng đọc dữ liệu mới, thay vì ép dữ liệu về trạng thái giả.

Ví dụ, đổi `PENDING_FRAUD_REVIEW` thành `PAID` để “đỡ lỗi” là sai về bảo mật. Đổi thành `CREATED` cũng không tự đúng nếu đã có các tác dụng phụ, thanh toán hoặc tác vụ idempotency dựa trên trạng thái mới.

## 5. Chiến lược expand–migrate–contract cho database

Một cách phổ biến để giữ khả năng rollback là chia thay đổi schema và dữ liệu thành nhiều giai đoạn thay vì làm tất cả trong cùng một release.

### 5.1. Expand: thêm cấu trúc theo hướng tương thích

Thay vì đổi tên cột ngay:

~~~sql
-- PostgreSQL, minh họa cột mới còn cho phép NULL
ALTER TABLE orders
  ADD COLUMN review_state VARCHAR(30) NULL;
~~~

Phiên bản cũ vẫn có thể đọc/ghi dữ liệu theo cột `status`. Phiên bản mới có thể bắt đầu ghi `review_state` khi cơ chế và thời điểm triển khai cho phép.

Trong giai đoạn này, tránh ép constraint khiến N-1 không thể viết, hoặc ngừng cập nhật trường cũ mà N-1 cần.

### 5.2. Migrate: hỗ trợ cả hai biểu diễn và chuyển dữ liệu

Phiên bản mới có thể đọc biểu diễn cũ và mới:

~~~text
Record chỉ có status cũ
        |
        v
Reader N hiểu và dùng dữ liệu cũ

Record có thêm review_state mới
        |
        v
Reader N hiểu review_state theo nghiệp vụ mới
~~~

Nếu cần đồng bộ dữ liệu trong giai đoạn chuyển tiếp, có thể dùng dual-write có kiểm soát, migration job, trigger hoặc outbox tùy kiến trúc. Phải xác định **trường nào là nguồn sự thật**, đảm bảo hai biểu diễn không bị lệch khi có retry, transaction rollback hoặc nhiều phiên bản ghi song song.

Dual-write không có nghĩa cứ ghi hai field là tương thích. Nếu trạng thái mới không có bản tương đương trong mô hình cũ, không thể tạo ra một ánh xạ trung thực chỉ bằng cách copy dữ liệu.

### 5.3. Contract: dọn cấu trúc cũ sau khi hết cửa sổ rollback

Chỉ khi tất cả consumer đã chuyển và không còn yêu cầu rollback về bản cũ:

~~~sql
-- Chỉ minh họa: thao tác phá vỡ compatibility,
-- không chạy trong giai đoạn rollback về N-1.
ALTER TABLE orders DROP COLUMN legacy_status;
~~~

Bước contract có thể bao gồm xóa cột, đổi enum type, thêm ràng buộc bắt buộc, bỏ compatibility layer hoặc đổi dạng event. Đây thường là giai đoạn **thay đổi khó/quá muộn để rollback code-only**.

### 5.4. Sơ đồ theo giai đoạn

~~~text
T0: N-1
  Schema cũ, dữ liệu cũ
        |
        v
T1: EXPAND
  Schema giữ cột cũ + thêm cột mới nullable
  N-1 vẫn đọc/ghi được
        |
        v
T2: ROLLBACK-COMPATIBLE RELEASE
  Các reader/consumer hiểu biểu diễn mới nếu cần
  Chưa bật ghi giá trị N-1 không hiểu
        |
        v
T3: ROLLOUT N
  Bật chức năng từng bước, canary
  Theo dõi các bản ghi/event mới
        |
        v
T4: CLOSE ROLLBACK WINDOW
  Công bố không còn quay lui code-only về N-1
        |
        v
T5: CONTRACT
  Xóa cấu trúc cũ, bật invariant mới, dọn cờ
~~~

Điểm quyết định ở T4 phải được công bố: từ đó kế hoạch sự cố thay đổi từ **rollback bản cũ** sang **roll-forward/hotfix hoặc remediation dữ liệu có kiểm soát**.

## 6. Phiên bản giao thức và event cần được quản lý riêng

Thay đổi database là một mặt của bài toán; ứng dụng Java thường còn trao đổi dữ liệu qua HTTP, gRPC, message queue, object storage và cache.

### 6.1. Người đọc cũ phải chịu được dữ liệu do người ghi mới tạo

Với một JSON API, thêm field mới có thể tương thích với consumer bỏ qua unknown fields. Nhưng đừng khẳng định tương thích nếu consumer thực hiện validation schema nghiêm ngặt hoặc serializes lại toàn bộ object.

Ví dụ sự kiện v1:

~~~json
{
  "eventType": "OrderPaid",
  "orderId": 42,
  "amountMinor": 120000
}
~~~

Sự kiện v2:

~~~json
{
  "eventType": "OrderPaid",
  "orderId": 42,
  "amountMinor": 120000,
  "currency": "VND",
  "riskReview": "PASSED"
}
~~~

Một consumer cũ có thể bỏ qua `currency` nhưng nếu sau này N ghi `currency=USD`, consumer cũ có thể diễn giải sai `amountMinor`. Schema evolution đúng về cú pháp không đảm bảo semantic compatibility.

### 6.2. Event mới cần xác định cách consumer cũ xử lý

Có ba tình huống chính:

1. **Event type cũ, field mới tương thích:** reader cũ có thể bỏ qua field chỉ khi không phá nghĩa cũ.
2. **Event type mới:** reader cũ cần chính sách được định nghĩa: bỏ qua an toàn, dừng xử lý, đưa vào DLQ hay không được giao event đó.
3. **Event cũ nhưng đổi semantics:** nguy hiểm nhất, vì reader cũ có thể âm thầm xử lý sai.

Với stream lưu lâu dài, event được tạo trong vài phút canary có thể được replay nhiều tháng sau. Kế hoạch rollback phải tính đến dữ liệu đã phát, không chỉ những event đến sau khi image cũ được bật lại.

### 6.3. Compatibility matrix của producer/consumer

| Producer | Consumer | Cần kiểm thử |
|---|---|---|
| N-1 | N-1 | Luồng cũ vẫn chạy |
| N-1 | N | N hiểu event/data lịch sử |
| N | N | Luồng mới hoạt động |
| **N** | **N-1** | **Điều kiện bắt buộc nếu rollback N-1 trong khi event N còn tồn tại** |

Ô cuối là trường hợp dễ bị bỏ sót trong pipeline CI vì nhiều nhóm chỉ test N với N hoặc N với dữ liệu cũ.

### 6.4. Các định dạng có schema registry

Với Avro, Protobuf hoặc định dạng có schema registry, nhóm cần xác định chính sách compatibility thực tế:

- Forward compatibility: reader cũ đọc được dữ liệu từ writer mới theo hợp đồng cụ thể.
- Backward compatibility: reader mới đọc được dữ liệu từ writer cũ.
- Full compatibility: hai hướng cần được đáp ứng theo quy tắc được áp dụng.

Tuy nhiên, dù registry chấp nhận schema, vẫn phải test cách ứng dụng xử lý **giá trị** mới, unknown enum, dữ liệu null, default, tính nhất quán của event ordering và tác dụng phụ.

Với Protobuf, không tái sử dụng field number đã xóa, cần reserve các field number/name phù hợp và kiểm tra cách thư viện hoặc bước chuyển đổi bảo toàn unknown fields. Với Java enum hoặc mapping từ string, cần xem logic xử lý giá trị lạ có thực sự an toàn không.

## 7. Read–modify–write: phép thử thường quan trọng hơn chỉ đọc

Một bản N-1 có thể đọc bản ghi v2 nhưng làm hỏng dữ liệu khi ghi lại.

Ví dụ trong JSON:

~~~json
{
  "id": 42,
  "name": "Minh",
  "riskReview": {
    "decision": "REVIEW",
    "explanation": "Requires manual approval"
  }
}
~~~

Model cũ:

~~~java
public class CustomerRecordV1 {
    public long id;
    public String name;
}
~~~

Nếu serializer cũ bỏ qua unknown fields và code cũ đọc rồi ghi đè toàn bộ record:

~~~text
JSON v2 -> DTO v1 -> update name -> JSON v1
~~~

thì `riskReview` sẽ biến mất nếu storage được thay thế toàn bộ. Nếu hệ thống dùng database columns và SQL cập nhật riêng `name`, dữ liệu ở cột mới có thể được giữ, nhưng không được tự giả định mọi ORM hoặc API đều hoạt động theo cách đó.

### 7.1. Những hành vi cần xác định cho reader cũ

- Nó fail rõ ràng với unknown fields/enum hay âm thầm bỏ qua?
- Nó ghi toàn bộ object hay chỉ những field thay đổi?
- Nó có dùng ORM entity merge/full replacement?
- Nó có serialize lại object vào queue hoặc cache?
- Nó có giữ unknown fields hoặc extension data không?
- Nó có tính toán giá trị dẫn xuất từ phần dữ liệu chưa hiểu?
- Nó có dùng optimistic locking/version column để phát hiện ghi đè đồng thời?

### 7.2. Bài test có ý nghĩa

~~~text
1. N tạo một record hợp lệ chứa field/giá trị mới
2. N-1 đọc record đó
3. N-1 sửa một field mà nó hiểu
4. N-1 ghi record trở lại
5. N đọc record cuối cùng
6. Xác minh phần dữ liệu do N thêm còn đúng và invariant còn nguyên
~~~

Nếu bước 2 thành công nhưng bước 6 thất bại, **rollback code-only không an toàn cho đường ghi đó**.

## 8. Quay lui khi có nhiều instance và ghi song song

Hệ thống có rolling deployment thường cho N và N-1 chạy đồng thời. Đây là thời điểm dữ liệu được trộn giữa hai phiên bản ngay cả trước khi một sự cố rollback xảy ra.

~~~text
Load balancer
     |
     +--> Instance N-1 --\
     |                   +--> Shared DB / Queue
     +--> Instance N ----/
~~~

Những vấn đề cần kiểm tra:

- N có ghi giá trị mới ngay khi bắt đầu phục vụ request không?
- N-1 có đọc record do N vừa ghi không?
- N-1 có cập nhật những bản ghi đó và làm mất field mới không?
- Background job trên N-1 có xử lý queue được N phát không?
- Có một instance bị lag hoặc một tác vụ batch chạy phiên bản cũ không?
- Có race condition do hai phiên bản duy trì hai diễn giải trạng thái?

Một dịch vụ không an toàn khi chạy hai phiên bản chung một kho dữ liệu có thể cần chiến lược rollout khác: **triển khai reader tương thích trước**, sau đó mới bật writer tạo định dạng mới. Chỉ canary ít phần trăm lưu lượng không đảm bảo an toàn nếu canary có thể ghi vào bảng dùng chung mà tất cả instance cũ đều đọc.

### 8.1. Feature flags và thời điểm bật writer mới

Tách **deploy N** khỏi **activate new writes**:

~~~text
Deploy N với code hỗ trợ format mới
           |
           v
New-write flag = OFF
           |
           v
Kiểm tra đọc/ghi dữ liệu cũ trên N
           |
           v
Cập nhật N-1 fallback nếu cần
           |
           v
Bật new-write flag theo cohort
           |
           v
Theo dõi record/event mới và rollback gate
~~~

Cờ phải kiểm soát **mọi đường ghi**: API, scheduler, consumer, batch job, administrative tool và migration script. Nếu chỉ tắt UI feature nhưng background consumer vẫn phát event mới, khả năng rollback vẫn có thể bị mất.

### 8.2. Cơ chế điều khiển rollback theo trạng thái dữ liệu

Đối với deploy controller tự động, nên phân biệt:

- **rollbackAllowed:** có thể trở về N-1 code-only.
- **newWritesEnabled:** có thể tạo trạng thái mới.
- **rollbackGateClosed:** đã ghi trạng thái không tương thích, không còn được rollback tự động về N-1.
- **dataRemediationRequired:** cần quy trình xử lý dữ liệu hoặc roll-forward.

Các giá trị này phải có nguồn dữ liệu và logic xác định tin cậy; không nên chỉ dựa trên cờ Boolean do một instance tự ghi, vì hệ thống phân tán còn có độ trễ, cache và batch bất đồng bộ. Gate cần đánh giá bằng bằng chứng về những record/event thực sự đã được tạo và những đường ghi chưa dừng.

## 9. Dữ liệu có thể không đảo ngược dù có script “down migration”

Một migration file có cả `up` và `down` chưa chứng minh dữ liệu quay lui an toàn.

### 9.1. Đổi kiểu làm mất thông tin

Ví dụ N làm tròn số tiền từ đơn vị nhỏ nhất hoặc đổi precision. Nếu dữ liệu bị làm tròn hay cắt bớt, không có hàm chuyển ngược bảo toàn hoàn toàn giá trị gốc.

### 9.2. Gộp nhiều trạng thái thành một trạng thái

N chuyển nhiều trạng thái cũ sang một trạng thái mới; sau đó không biết record đã thuộc trạng thái nào trước đây. Đảo schema không phục hồi được phân biệt đã mất.

### 9.3. Xóa hoặc mã hóa lại dữ liệu

Nếu N xóa field chứa thông tin quan trọng, thay đổi khóa mã hóa hoặc di chuyển dữ liệu không giữ bản gốc, việc chạy down migration có thể không phục hồi được các giá trị mất.

### 9.4. Tác dụng phụ bên ngoài

Nếu N đã phát yêu cầu thanh toán hoặc email, rollback database không tự thu hồi chúng. Có thể cần **compensating action**, nhưng hành động bù không giống hoàn nguyên thời gian: giao dịch hoàn tiền vẫn khác một thanh toán chưa từng xảy ra.

### 9.5. Backup restore không phải rollback không mất dữ liệu

Khôi phục một snapshot trước rollout có thể đưa database về trạng thái N-1 hiểu, nhưng đồng thời **mất những ghi chép hợp lệ** được tạo sau thời điểm snapshot, trừ khi có cơ chế phục hồi/chuyển tiếp và đối soát thích hợp.

Trước khi coi đây là phương án, phải xác định:

- **RPO (Recovery Point Objective):** mức mất dữ liệu được phép.
- **RTO (Recovery Time Objective):** thời gian gián đoạn có thể chấp nhận.
- Backup/snapshot có nhất quán giữa database và event log không?
- Có thể replay một cách idempotent những transaction hợp lệ không?
- Đã đối soát side effects ở dịch vụ khác chưa?
- Ai có quyền quyết định mất dữ liệu hoặc bồi hoàn nghiệp vụ?

Không nên coi `restore backup` là một bước “an toàn hiển nhiên” trong deployment script.

## 10. Các chiến lược khi N đã ghi dữ liệu không tương thích

Khi rollback code-only không còn đủ điều kiện, có một số hướng xử lý. Phương án cần được chọn theo tác động thực tế, không dựa vào mong muốn quay về bản cũ bằng mọi giá.

### 10.1. Roll-forward bằng hotfix

Giữ phiên bản có khả năng hiểu dữ liệu mới, phát hành bản vá cho regression gây sự cố.

Ưu điểm: tránh buộc data quay về representation cũ, thường phù hợp khi N đã tạo trạng thái mới không thể chuyển ngược.

Hạn chế: yêu cầu đội ngũ có khả năng sửa và phát hành nhanh; bản vá cũng phải được kiểm thử trên dữ liệu đã ghi.

### 10.2. Rollback về một bản N-1+ tương thích dữ liệu

Nếu đã chuẩn bị trước một phiên bản fallback hiểu data/event mới nhưng chưa bật các tính năng gây regression, có thể triển khai bản đó thay vì N-1 nguyên thủy.

Ưu điểm: khôi phục logic ổn định và giữ dữ liệu v2.

Hạn chế: cần chuẩn bị trước; không thể giả định binary cũ tự đọc được mọi trạng thái mới.

### 10.3. Khoanh vùng dữ liệu mới và dừng writer

Nếu chỉ một cohort nhỏ có dữ liệu v2, có thể dừng ghi, tách lưu lượng, duy trì một service chuyên đọc v2 hoặc chặn N-1 truy cập các record đó trong lúc xử lý.

Ưu điểm: giảm phạm vi ảnh hưởng.

Hạn chế: tăng phức tạp định tuyến, phân quyền và vận hành; không phù hợp nếu dữ liệu đã lan rộng qua quan hệ và event.

### 10.4. Data remediation có kiểm chứng

Chỉ dùng khi có phép chuyển đổi **bảo toàn nghĩa hoặc được nghiệp vụ chấp thuận** từ dữ liệu mới sang dạng mà N-1 hiểu.

Một quy trình tối thiểu:

1. Dừng writer phát sinh trạng thái mới.
2. Chụp snapshot/backup và lưu checkpoint.
3. Truy vấn chính xác những bản ghi/event bị ảnh hưởng.
4. Xây dựng ánh xạ có kiểm tra invariant.
5. Thử chuyển đổi trên bản sao dữ liệu.
6. Đối soát tổng số, số tiền, trạng thái và mối quan hệ.
7. Phê duyệt phần mất nghĩa (nếu có) bởi người chịu trách nhiệm nghiệp vụ.
8. Chạy chuyển đổi có audit, retry/idempotency và kế hoạch khôi phục.
9. Chỉ sau đó mới triển khai N-1 và xác minh.

Nếu không tồn tại ánh xạ an toàn, data remediation không phải một lựa chọn hợp lệ.

### 10.5. Restore snapshot có kế hoạch reconciliation

Trong tình huống nghiêm trọng, có thể cần restore một mốc trước khi N ghi trạng thái không tương thích. Nhưng phải có phương án xử lý dữ liệu hợp lệ phát sinh trong khoảng thời gian bị mất và đối chiếu event/transaction ở hệ thống ngoài.

Đây là **disaster recovery**, không phải thao tác rollback code thông thường. Quyết định phải theo RPO/RTO và quyền phê duyệt đã định.

## 11. Quy trình ra quyết định rollback khi gặp sự cố

Không nên đặt tiêu chí duy nhất là “healthcheck của N đang đỏ”. Trước khi đưa N-1 lên production, cần chạy các gate dữ liệu và giao thức.

~~~text
N gặp sự cố sau rollout
          |
          v
Có bằng chứng N đã ghi trạng thái mới?
          |
    +-----+------+
    |            |
   Chưa          Có / chưa chắc
    |            |
    v            v
Kiểm tra       Dừng/khóa các writer liên quan,
rollback       đo phạm vi dữ liệu và event mới
compatibility        |
    |                v
    |         N-1 đọc, xử lý và ghi lại
    |         dữ liệu đó an toàn?
    |                |
    |         +------+------+
    |         |             |
    |        Có           Không
    |         |             |
    v         v             v
Rollback    Rollback    Không rollback code-only
code-only   có giám sát  Chọn hotfix, N-1+, khoanh vùng
sau gate                 hoặc remediation có kiểm chứng
~~~

Câu hỏi “chưa chắc N đã ghi” **không được tự động xem là “chưa ghi”**. Đặc biệt với queue, batch và các instance nằm ngoài hệ quan sát, thiếu log không phải bằng chứng không có thay đổi.

### 11.1. Các bước vận hành trước rollback

- Chặn hoặc giảm lưu lượng gây ghi mới nếu điều đó phù hợp với kế hoạch incident.
- Vô hiệu hóa feature flag và background writer tạo trạng thái không tương thích.
- Kiểm tra request đang xử lý, transaction đang mở, in-flight messages và retry.
- Ghi nhận thời điểm bắt đầu rollout, những instance N đã nhận lưu lượng và số record/event mới.
- Chụp snapshot phù hợp với tính nhất quán của hệ thống trước khi sửa dữ liệu.
- Xác minh N-1 còn tương thích với schema và hạ tầng đang chạy.
- Ra quyết định rollback code-only hoặc đường phục hồi khác dựa trên bằng chứng.

Tắt feature flag ở một control plane chưa chứng minh mọi writer đã dừng. Cần xác nhận trạng thái trên thực tế ở worker, scheduler và kết nối ngoài.

### 11.2. Sau khi rollback

Kiểm tra ít nhất:

- N-1 khởi động và đọc được dữ liệu mới còn tồn tại.
- Các request quan trọng chạy đúng, không chỉ health endpoint.
- Không có tăng vọt của parse errors, unknown enum, DB constraint violations.
- Queue consumer không mắc kẹt ở poison message hoặc tăng DLQ.
- Không có mất field v2 khi N-1 cập nhật bản ghi.
- Business invariants, tiền và trạng thái vẫn nhất quán.
- Có phương án cho dữ liệu v2 chưa thể xử lý ngay.

Rollback hoàn tất về mặt deployment không đồng nghĩa incident đã kết thúc.

## 12. Ma trận kiểm thử bắt buộc cho rollback

Để chứng minh khả năng N-1 xử lý dữ liệu do N ghi, có thể chuẩn bị một môi trường có bản sao schema, dữ liệu đại diện, queue và service dependencies.

| Test | Setup | Kỳ vọng |
|---|---|---|
| Old reader ↔ old data | N-1 đọc dữ liệu N-1 | Không regression nền |
| New reader ↔ old data | N đọc dữ liệu N-1 | Hỗ trợ dữ liệu legacy |
| New reader ↔ new data | N tạo và đọc dữ liệu N | Tính năng mới chạy đúng |
| **Old reader ↔ new data** | **N ghi, N-1 đọc** | **Không crash/không diễn giải sai** |
| **Old writer ↔ new data** | **N ghi, N-1 cập nhật, N đọc lại** | **Không mất field, không phá invariant** |
| Mixed-version writes | N và N-1 cùng ghi vào shared store | Không race gây lệch trạng thái |
| Consumer downgrade | N phát event, consumer N-1 đọc | Xử lý hoặc từ chối đúng chính sách |
| Replay/history | N-1 đọc lại log/snapshot có event N | Không lặp side effect hoặc mắc kẹt |
| Cache downgrade | N ghi cache, N-1 đọc | Không deserialization error hoặc xử lý được invalidation |
| Schema rollback check | N-1 chạy trên schema sau migration | Mọi SQL/read/write quan trọng vẫn hoạt động |
| Failure-injection | N dừng giữa migration/dual-write | Recovery và đối soát có thể thực hiện |

### 12.1. Test định dạng có tính quyết định

Chỉ cần một test “serialize rồi deserialize ngay trong N” là chưa đủ. Cần lưu các *golden fixtures* do từng writer version tạo ra và chạy reader của những phiên bản thực sự còn hỗ trợ.

Ví dụ, với JSON:

~~~text
fixtures/
  orders-v1.json
  orders-v2-with-new-field.json
  orders-v2-with-new-enum.json
  orders-v2-null-and-defaults.json
~~~

Với Java serialization, lưu fixture binary theo những phiên bản thực tế, đánh giá `serialVersionUID`, class hierarchy và `readObject`/`writeObject` nếu chúng được sử dụng. Với Protobuf, test cả unknown enum/field và các bước chuyển tiếp qua JSON nếu hệ thống có chuyển đổi dạng.

### 12.2. Test trên đúng JDK và dependency

Trong Java migration, có thể có hai chiều biến đổi cùng lúc:

~~~text
Ứng dụng N-1 chạy JDK cũ
              |
              v
Ứng dụng N chạy JDK mới
              |
              v
Dữ liệu mới được ghi
              |
              v
Rollback N-1 trên JDK nào?
~~~

Nếu rollback N-1 cần trở lại JDK cũ, phải xác định hạ tầng còn hỗ trợ JDK đó không và mọi dữ liệu mới có thể được reader cũ xử lý không. Nếu N-1 chạy trên JDK mới, binary N-1 phải được kiểm thử với JDK/dependency mới. Cả hai phương án đều có rủi ro riêng.

Một bộ test ghi rõ JDK vendor/build, application version, driver, database version và effective config sẽ giúp phân biệt lỗi dữ liệu với lỗi runtime compatibility.

### 12.3. Test đường ghi gián tiếp

Đừng chỉ test HTTP endpoint chính. Các đường sau cũng có thể tạo dữ liệu mà N-1 không hiểu:

- Database migration/backfill.
- Job theo lịch.
- Kafka/RabbitMQ consumer.
- Retry/outbox publisher.
- CDC transformation.
- Cơ chế cache warming.
- Operator script.
- Tính năng admin hoặc import/export.
- Plugin hoặc hệ thống tích hợp bên ngoài.

Rollback gate phải tính đến tất cả các nguồn này.

## 13. Monitoring và bằng chứng đóng/mở cửa sổ rollback

Có thể thiết lập metric/alert để theo dõi dữ liệu có khả năng chặn rollback:

| Metric/tín hiệu | Ý nghĩa |
|---|---|
| `new_format_records_created_total` | Đã có bản ghi thuộc định dạng mới |
| `new_enum_values_written_total` | Đã xuất hiện trạng thái mà N-1 có thể không hiểu |
| `event_schema_v2_published_total` | Đã phát message theo schema mới |
| `old_reader_unknown_values_total` | Reader cũ gặp giá trị lạ |
| `old_reader_roundtrip_failures_total` | Cập nhật bằng writer cũ làm sai dữ liệu |
| `migration_backfill_completed` | Đã thực hiện bước biến đổi dữ liệu |
| `dual_write_mismatch_total` | Hai biểu diễn đang lệch |
| `dlq_messages_total` | Consumer không xử lý được thông điệp |
| `rollback_gate_state` | Trạng thái cho phép/không cho phép rollback code-only |

Tên metric chỉ là gợi ý thiết kế. Cần đảm bảo metric phản ánh sự thật hệ thống, không chỉ việc một dòng code được gọi. Dùng log, query DB, event metadata và checkpoint để đối chiếu khi quyết định rollback.

### 13.1. Mốc đóng cửa sổ rollback phải tường minh

Một release có thể được chia thành:

- **Rollback-safe phase:** N chưa ghi trạng thái vượt khả năng N-1.
- **Conditional rollback phase:** N đã ghi dữ liệu mới nhưng tồn tại biện pháp chuyển đổi được kiểm chứng hoặc bản fallback N-1+.
- **Rollback-gate closed:** N đã ghi trạng thái không thể xử lý an toàn bằng N-1; chỉ được dùng phương án phục hồi thay thế.

Việc đóng gate nên có người phụ trách, thời điểm, lý do và thông báo đến nhóm vận hành. Một cơ chế auto-rollback không biết về dữ liệu đã ghi nên được giới hạn hoặc vô hiệu hóa sau khi cửa sổ rollback code-only đóng.

## 14. Chuẩn bị runbook thay vì chỉ ghi “kubectl rollout undo”

Một runbook hữu ích cần cho operator biết **khi nào được rollback**, **khi nào phải dừng** và **dữ liệu nào cần kiểm tra**.

### 14.1. Mẫu quyết định trước khi rollback

~~~text
Incident ID:
Thời điểm deploy N:
Phiên bản N / N-1:
JDK và vendor/build hiện tại:
Database schema revision:
Feature flags tạo format mới:
Writers đã dừng chưa:
Số record N-only hoặc chưa xác định:
Số event N-only trong queue/log:
N-1 đọc dữ liệu N thành công:
N-1 read-modify-write giữ invariants:
External side effects đã đối soát:
Backup/snapshot/checkpoint:
RPO/RTO nếu cần restore:
Quyết định: CODE-ONLY / N-1+ / ROLL-FORWARD / DATA REMEDIATION / DR
Người phê duyệt:
Điều kiện xác minh sau thao tác:
~~~

### 14.2. Quy tắc dừng khẩn cấp

Nếu gặp một trong các điều kiện sau, không nên tự động đưa N-1 trở lại chỉ vì nó là image cũ:

- N đã ghi trạng thái enum mới mà N-1 xử lý sai hoặc không hiểu.
- N đã biến đổi/xóa dữ liệu cũ một cách không đảo ngược.
- Cấu trúc DB hiện tại từ chối các câu lệnh ghi cần thiết của N-1.
- Event hoặc checkpoint mới không thể được consumer N-1 xử lý an toàn.
- N-1 đọc được nhưng ghi lại làm mất thông tin bắt buộc của N.
- Không xác định được phạm vi dữ liệu v2 trong khi side effect nghiệp vụ có tính quan trọng cao.

Trong những trường hợp này, phải chuyển sang kế hoạch ứng cứu có kiểm soát và giữ bằng chứng. “Dừng rollback” không có nghĩa bỏ mặc sự cố; nó có nghĩa chọn phương án khác không gây sai lệch dữ liệu.

## 15. Các sai lầm phổ biến

**“Rollback chỉ cần thay image.”** Không đúng khi dữ liệu, schema, event và side effects đã đổi.

**“Schema migration có file down nên luôn đảo được.”** Không. Down script có thể đổi cấu trúc mà không phục hồi dữ liệu đã mất hoặc đã đổi nghĩa.

**“JSON thêm field mới là luôn backward-compatible.”** Không nhất thiết. Reader cũ có thể validate nghiêm ngặt, mất field khi ghi lại hoặc không hiểu nghĩa của dữ liệu mới.

**“Unknown enum có nhánh default thì an toàn.”** Không nếu default gán nghĩa nghiệp vụ sai. Trạng thái rủi ro cần fail closed hoặc cơ chế tương thích được thiết kế trước.

**“N-1 đọc được record N thì rollback được.”** Cần kiểm tra N-1 cập nhật record và các invariant sau khi ghi.

**“Canary chỉ có 1% lưu lượng thì dữ liệu mới không ảnh hưởng phần còn lại.”** Nếu cùng dùng DB/queue, một record hoặc event mới có thể được tất cả instance cũ xử lý.

**“Tắt feature flag là đảm bảo không có dữ liệu mới.”** Các request đang xử lý, background job, retry và outbox có thể tiếp tục ghi/phát.

**“Backup có thể đưa hệ thống trở về trạng thái hoàn hảo.”** Restore có thể mất giao dịch hợp lệ; cần RPO, reconciliation và đối soát side effects.

**“Tương thích Protobuf/Avro schema nghĩa là ứng dụng hoàn toàn tương thích.”** Schema hợp lệ không tự đảm bảo semantic compatibility và không mất unknown data qua các bước chuyển đổi.

**“Nếu rollback thất bại thì cứ chạy migration đảo và thử lại.”** Điều này có thể làm tình trạng dữ liệu tệ hơn. Cần snapshot, xác định nguyên nhân và chọn phương án phục hồi có kiểm chứng.

**“Chỉ phải kiểm tra dữ liệu trong database chính.”** Event logs, cache, object storage, search index, CDC, checkpoint và hệ thống bên ngoài cũng có thể giữ trạng thái của phiên bản mới.

## 16. Checklist đánh giá rollback khi N đã ghi dữ liệu

- [ ] Đã phân biệt rollback code, schema, data, event và business side effects.
- [ ] Đã kiểm kê những format/state/enum mới mà N có thể ghi.
- [ ] Đã chứng minh N-1 đọc đúng dữ liệu do N tạo.
- [ ] Đã kiểm thử N-1 read–modify–write không mất field hoặc phá invariant.
- [ ] Đã xác nhận N-1 không gán nghĩa sai cho unknown values.
- [ ] Đã kiểm tra migration schema không chặn SQL của N-1.
- [ ] Đã xác định thời điểm bật new-write flag và các đường ghi background.
- [ ] Đã kiểm thử N và N-1 khi chạy đồng thời trên shared data store.
- [ ] Đã kiểm tra event/message, schema registry và các consumer cũ.
- [ ] Đã kiểm tra serialization/cache/object storage và plugin liên quan.
- [ ] Đã test trên các JDK/runtime thực sự có thể rollback về.
- [ ] Đã có golden fixtures, test chéo version và test replay.
- [ ] Đã xác định những phép chuyển đổi dữ liệu không thể đảo ngược.
- [ ] Đã xác định RPO/RTO và cách đối soát nếu cần restore backup.
- [ ] Đã đo phạm vi dữ liệu mới thực sự được ghi trong rollout.
- [ ] Đã xác nhận feature flags và tất cả writer có thể dừng.
- [ ] Đã công bố rollback gate và người phê duyệt.
- [ ] Đã chuẩn bị roll-forward/hotfix hoặc fallback N-1+ nếu N-1 không tương thích.
- [ ] Đã chuẩn bị kiểm thử xác minh sau rollback và kế hoạch xử lý dữ liệu v2 còn lại.

## 17. Kết luận

Điều kiện quan trọng nhất để quay lui sau khi phiên bản mới đã ghi dữ liệu là: **phiên bản được quay về phải tiếp tục đọc, hiểu, xử lý và ghi an toàn những trạng thái mà phiên bản mới đã tạo ra**. Khả năng khởi động JAR cũ, kết nối database thành công hoặc có file `down migration` không đủ để chứng minh điều đó.

Trong Java Advance Compatibility Migration, hãy nhìn rollback như một **hợp đồng xuyên suốt code–schema–data–protocol–runtime**. Chuẩn bị schema theo expand–migrate–contract, tách deploy khỏi việc bật writer mới, thử ma trận N/N-1 và đặc biệt là read–modify–write, rồi đóng cửa sổ rollback một cách tường minh khi dữ liệu trở nên không tương thích.

Nếu dữ liệu mới đã được ghi và không có phép chuyển đổi bảo toàn nghĩa, không nên rollback code-only một cách mù quáng. Khi đó lựa chọn an toàn hơn có thể là **roll-forward bằng hotfix, dùng bản fallback đã hiểu format mới, khoanh vùng dữ liệu hoặc phục hồi có đối soát**, tùy yêu cầu nghiệp vụ và RPO/RTO. Một kế hoạch rollback tốt không chỉ nói cách quay lại phiên bản cũ, mà còn biết **khi nào không được quay lại**.
