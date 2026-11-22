# QUORUM và EACH_QUORUM trong các thao tác được hỗ trợ của Apache Cassandra

## 1. Bối cảnh: cùng chữ “quorum”, khác phạm vi xác nhận

Trong Apache Cassandra, mỗi bảng **wide-column** được thiết kế theo kiểu truy vấn mà ứng dụng phải phục vụ. **Partition key** quyết định token của dữ liệu; **replication strategy** quyết định các replica giữ dữ liệu tại từng datacenter (DC); **consistency level** (CL) quyết định điều kiện xác nhận cho từng request đọc hoặc ghi.

Khi cluster chỉ có một datacenter, nhiều ví dụ thường giới thiệu quorum như “đa số replica”. Khi trải dữ liệu sang **nhiều datacenter**, câu hỏi quan trọng trở thành: **đa số trên toàn bộ replica hay đa số ở từng datacenter?**

- **`QUORUM`:** cần quorum tính trên **tổng replication factor của những DC liên quan đến keyspace**. Các ACK có thể đến từ các DC với tỷ lệ khác nhau, miễn tổng số đạt ngưỡng.
- **`EACH_QUORUM`:** đối với **ghi được hỗ trợ**, cần quorum **trong mỗi datacenter** được cấu hình replication. Một DC không đủ ACK thì không đạt mức này, dù tổng ACK đã vượt ngưỡng `QUORUM`.
- **`LOCAL_QUORUM`:** cần quorum ở **datacenter cục bộ** của coordinator/request; đây là lựa chọn thường được cân nhắc khi muốn tránh phụ thuộc vào độ trễ hoặc sự cố WAN ở đường request.

Bài thuộc chương **Nhiều trung tâm dữ liệu** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Mục tiêu là biết **thao tác nào chấp nhận `QUORUM` hoặc `EACH_QUORUM`**, tính đúng số ACK, hiểu ảnh hưởng tới availability/latency, và chọn consistency hợp lý cho CQL và ứng dụng Java.

> Ghi nhớ ngay từ đầu: **`EACH_QUORUM` không phải “quorum mạnh hơn” có thể gắn cho mọi câu CQL**. Trong Apache Cassandra, mức này được thiết kế cho **ghi**, không phải consistency level hợp lệ cho truy vấn `SELECT` thông thường.

## 2. Nền tảng: replication theo datacenter

### 2.1. NetworkTopologyStrategy

Với triển khai đa DC, keyspace thường dùng `NetworkTopologyStrategy` để khai báo số replica **riêng cho từng datacenter**, thay vì chỉ một RF chung:

~~~cql
CREATE KEYSPACE shop_global
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_hanoi': 3,
    'dc_singapore': 3
}
AND durable_writes = true;
~~~

Ví dụ này giả định topology đã có hai DC với tên chính xác `dc_hanoi` và `dc_singapore`, mỗi DC đủ ít nhất ba node phù hợp. RF tổng cho **một partition** theo keyspace là **3 + 3 = 6** bản sao, trước khi xét các tình trạng node cụ thể.

**Không nhầm RF với số node toàn cluster:** dù mỗi DC có mười node, một partition ở ví dụ vẫn được nhân bản **ba lần trong mỗi DC**, không phải trên tất cả node.

Cassandra chọn replica dựa trên token/partition key, chiến lược replication và topology (DC/rack). Cấu hình snitch, rack, số node và phân bố token phải tương thích. Nếu RF lớn hơn số node có thể đặt replica trong một DC, ví dụ bên dưới sẽ không còn phản ánh một triển khai lành mạnh.

### 2.2. Công thức quorum

Với một partition có tổng replication factor `RF_total`:

~~~text
QUORUM toàn cụm = floor(RF_total / 2) + 1

LOCAL_QUORUM trong DC i = floor(RF_i / 2) + 1

EACH_QUORUM cho ghi = phải có ít nhất LOCAL_QUORUM
                      ở MỖI DC có RF_i được khai báo
~~~

`floor` là lấy phần nguyên xuống. Các công thức mô tả **số replica cần xác nhận** cho ví dụ với placement phù hợp; chưa tính timeout, lỗi mạng hay node bị quá tải. Chúng cũng không có nghĩa mọi replica còn lại chắc chắn đã nhận xong dữ liệu ở lúc client được trả về.

Với RF tại mỗi DC bằng 3:

- `RF_total = 6` nên `QUORUM = floor(6/2)+1 = 4`.
- `LOCAL_QUORUM` tại mỗi DC yêu cầu **2/3** ACK.
- `EACH_QUORUM` với ghi yêu cầu **2 ACK ở Hà Nội và 2 ACK ở Singapore**; tổng ít nhất 4, nhưng phải đúng phân bố từng DC.

## 3. So sánh ba consistency level quan trọng

| Mức nhất quán | Phạm vi xác nhận | SELECT thông thường | INSERT / UPDATE / DELETE thông thường | Phụ thuộc kết nối liên DC |
|---|---|---|---|---|
| `LOCAL_QUORUM` | Đa số replica trong DC cục bộ | Hỗ trợ | Hỗ trợ | Có thể tránh phụ thuộc DC khác trên critical path |
| `QUORUM` | Đa số replica trên tổng RF các DC | Hỗ trợ | Hỗ trợ | Có thể phải đợi replica ở DC khác, tùy RF/placement và số ACK |
| `EACH_QUORUM` | Đa số replica **trong từng DC** | **Không hỗ trợ cho SELECT** | Hỗ trợ đối với ghi thích hợp | Phải đủ ACK từ **mọi DC** được yêu cầu |

**Các ô trên nói về regular reads/writes thông thường.** Những loại thao tác có điều kiện (LWT), counter, batch, hoặc feature đặc biệt có thêm quy tắc riêng theo phiên bản/protocol. Không tự suy luận chỉ từ bảng này rằng một CL được phép trong mọi biến thể câu lệnh.

### 3.1. `QUORUM` có thể đạt được bằng `3 + 1`

Với DC Hà Nội (RF=3) và DC Singapore (RF=3), cần ít nhất bốn ACK.

Nếu có **3 ACK từ Hà Nội và 1 ACK từ Singapore**, request dùng `QUORUM` đã đạt ngưỡng 4. Nhưng nó **chưa đạt `EACH_QUORUM`**, vì Singapore mới có 1/3 ACK, thấp hơn quorum của DC đó là 2.

Nếu có **2 ACK từ mỗi DC**, cả `QUORUM` lẫn `EACH_QUORUM` đều có thể được đáp ứng.

### 3.2. `LOCAL_QUORUM` không bảo đảm DC khác đã nhận

Nếu ứng dụng gửi ghi qua coordinator trong `dc_hanoi` với `LOCAL_QUORUM`, hai replica ở Hà Nội xác nhận là đủ theo CL. Các replica của Singapore có thể nhận mutation sau đó qua cơ chế ghi/khôi phục, nhưng **thành công của request không có nghĩa Singapore đã xác nhận quorum**.

Điều này hữu ích cho availability và latency cục bộ, nhưng yêu cầu nghiệp vụ phải chấp nhận một **khoảng sai lệch tạm thời giữa DC**. Nếu cần ràng buộc chặt về trạng thái đã được ghi ở mỗi DC, hãy xem xét `EACH_QUORUM` cho ghi và đánh đổi của nó.

## 4. Bảng kết quả: số ACK theo từng DC quyết định điều gì?

Giả sử `RF_HN = 3`, `RF_SG = 3`. Trong bảng dưới, mỗi ô `HN + SG` là số replica **thực sự ACK cho request** trong hai DC. Để so `LOCAL_QUORUM`, giả sử coordinator cục bộ ở **Hà Nội**.

| ACK HN + SG | Tổng ACK | `QUORUM` (cần 4) | `EACH_QUORUM` ghi (cần 2+2) | `LOCAL_QUORUM` HN (cần 2) |
|---|---:|---|---|---|
| 3 + 1 | 4 | Đạt | **Không đạt** | Đạt |
| 2 + 2 | 4 | Đạt | Đạt | Đạt |
| 1 + 3 | 4 | Đạt | **Không đạt** | **Không đạt** |
| 3 + 0 | 3 | Không đạt | Không đạt | Đạt |
| 2 + 1 | 3 | Không đạt | Không đạt | Đạt |
| 1 + 2 | 3 | Không đạt | Không đạt | Không đạt |
| 0 + 3 | 3 | Không đạt | Không đạt | Không đạt |
| 3 + 3 | 6 | Đạt | Đạt | Đạt |

Đây là **mô hình toán học theo số ACK**, không bảo đảm mọi tập ACK nêu trên thực tế đã xảy ra theo cùng thứ tự. Với request thật còn có replica selection, thời hạn chờ, mạng, lỗi và quá tải. Đừng đồng nhất “đủ node đang UP” với “chắc chắn đủ ACK đúng hạn”.

### Sơ đồ so sánh hai cách đạt tổng bốn ACK

~~~mermaid
flowchart TD
    A["Ghi đến keyspace RF=3 + RF=3"] --> B{"Đã nhận ACK nào?"}
    B --> C["Hà Nội: 3, Singapore: 1"]
    B --> D["Hà Nội: 2, Singapore: 2"]
    C --> E["QUORUM: ĐẠT vì tổng = 4"]
    C --> F["EACH_QUORUM: KHÔNG ĐẠT vì SG thiếu quorum"]
    D --> G["QUORUM: ĐẠT vì tổng = 4"]
    D --> H["EACH_QUORUM: ĐẠT vì mỗi DC có 2 ACK"]
~~~

Như vậy **`EACH_QUORUM` mạnh hơn `QUORUM` ở yêu cầu phân bổ ACK khi ghi trên nhiều DC**, chứ không đơn thuần tăng số ACK tối thiểu trong mọi cấu hình.

## 5. Trường hợp RF không đều: phải tính từng DC

Giả sử hai datacenter có replication không đối xứng:

~~~cql
ALTER KEYSPACE shop_global
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc_hanoi': 3,
    'dc_singapore': 2
};
~~~

Đây là câu lệnh **minh họa cú pháp**, không phải khuyến nghị chỉnh RF ngay trên production. Thay RF của keyspace đang chạy là thay đổi topology dữ liệu và cần quy trình repair/streaming, kiểm tra replica placement và giám sát thích hợp.

Với `RF_total = 3 + 2 = 5`:

- `QUORUM = floor(5/2)+1 = 3` ACK **toàn bộ**.
- `LOCAL_QUORUM` Hà Nội = `floor(3/2)+1 = 2`.
- `LOCAL_QUORUM` Singapore = `floor(2/2)+1 = 2`.
- `EACH_QUORUM` ghi = **ít nhất 2 ACK tại Hà Nội và 2 ACK tại Singapore**, tổng ít nhất 4 ACK.

Ví dụ ACK **3 + 0**:

- `QUORUM` đạt 3.
- `EACH_QUORUM` không đạt vì Singapore chưa có ACK.

Ví dụ ACK **1 + 2**:

- `QUORUM` đạt 3.
- `EACH_QUORUM` không đạt vì Hà Nội chưa đủ 2.

Ví dụ ACK **2 + 2**: cả hai đạt.

Kết luận: **quorum theo từng DC không thể được tính bằng một phép chia RF_total duy nhất**. Mỗi lần RF thay đổi hoặc thêm DC có replica, phải lập lại bảng điều kiện ACK.

## 6. Hỗ trợ thao tác: điểm phân biệt bắt buộc

### 6.1. Ghi thường: `EACH_QUORUM` có ý nghĩa

Các thao tác mutation thông thường có thể yêu cầu phân bố ACK theo từng DC:

~~~cql
CREATE TABLE shop_global.order_by_id (
    order_id uuid PRIMARY KEY,
    status text,
    updated_at timestamp
);

-- Chạy trong cqlsh, với topology hỗ trợ như ví dụ.
CONSISTENCY EACH_QUORUM;

INSERT INTO shop_global.order_by_id
    (order_id, status, updated_at)
VALUES
    (11111111-1111-1111-1111-111111111111,
     'CONFIRMED',
     '2026-11-21T10:00:00Z');

UPDATE shop_global.order_by_id
SET status = 'SHIPPED',
    updated_at = '2026-11-21T10:05:00Z'
WHERE order_id = 11111111-1111-1111-1111-111111111111;

DELETE FROM shop_global.order_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
~~~

Trong ví dụ, mỗi lệnh ghi cần quorum ở **từng DC**. Khi một DC mất khả năng phản hồi đủ replica, write có thể gặp unavailable/timeout. **Không dùng `EACH_QUORUM` như một cơ chế giao dịch**: nó không kiểm tra điều kiện nghiệp vụ hay ngăn hai writer cập nhật cùng cell.

### 6.2. Đọc: dùng `QUORUM` hoặc `LOCAL_QUORUM`, không dùng `EACH_QUORUM`

Để đọc:

~~~cql
CONSISTENCY QUORUM;

SELECT order_id, status, updated_at
FROM shop_global.order_by_id
WHERE order_id = 11111111-1111-1111-1111-111111111111;
~~~

`QUORUM` là mức đọc được hỗ trợ; replica tham gia có thể ở nhiều DC, tùy placement và cách đạt quorum.

**Không viết một ứng dụng phụ thuộc vào `SELECT` với CL `EACH_QUORUM`.** Mức này **không hỗ trợ cho read thông thường**; ngay cả nếu công cụ client cho phép chọn tên mức nhất quán, server có thể từ chối request SELECT tương ứng.

Nếu mục tiêu là “đọc dữ liệu có xác nhận ở từng DC”, phải **thiết kế cặp write/read CL** phù hợp, thay vì cố dùng `EACH_QUORUM` cho SELECT.

### 6.3. Bảng phạm vi thao tác và sự cẩn trọng

| Loại yêu cầu | `QUORUM` | `EACH_QUORUM` | Điều cần ghi nhớ |
|---|---|---|---|
| `SELECT` đọc row/partition bình thường | Hỗ trợ | **Không hỗ trợ** | Không có “read EACH_QUORUM” |
| `INSERT` thông thường | Hỗ trợ | Hỗ trợ cho ghi | Xác nhận phân bố ACK, không tạo uniqueness |
| `UPDATE` không có `IF` | Hỗ trợ | Hỗ trợ cho ghi | Timestamp/last-write-wins vẫn áp dụng |
| `DELETE` không có `IF` | Hỗ trợ | Hỗ trợ cho ghi | Tombstone và repair vẫn cần được quản lý |
| `INSERT/UPDATE ... IF ...` (LWT) | Có phần CL ghi/commit riêng | **Không suy rộng** từ ghi thường | Cần thêm `SERIAL`/`LOCAL_SERIAL` và xác minh phiên bản |
| Batch/counter/operation đặc thù | Kiểm tra điều kiện riêng | Kiểm tra quy tắc phiên bản | Không xem tính chất ACK là ACID hoặc CAS |

Không biến một bảng tóm tắt thành khẳng định rằng mọi tính năng CQL đều hỗ trợ cả hai mức. Phải tra đặc điểm của **loại request thực tế** và bản Cassandra đang sử dụng khi làm việc với counters, logged batches, LWT hoặc các tính năng có đường thực thi riêng.

## 7. So sánh tính sẵn sàng khi một datacenter gặp sự cố

### 7.1. Hai datacenter RF=3+3

Nếu **Singapore mất hoàn toàn**, Hà Nội vẫn có tối đa 3 ACK cho một partition:

- `LOCAL_QUORUM` tại Hà Nội cần **2/3**, nên có thể tiếp tục phục vụ write/read cục bộ khi các điều kiện khác còn tốt.
- `QUORUM` toàn bộ cần **4/6**, nên **không đủ** chỉ với 3 replica ở Hà Nội.
- `EACH_QUORUM` ghi cần **2/3 tại cả hai DC**, nên cũng **không đủ**.

Do đó trong mô hình 3+3, **cả `QUORUM` và `EACH_QUORUM` đều không chịu được việc mất nguyên một DC** đối với yêu cầu ghi; khác biệt giữa chúng vẫn quan trọng khi **chỉ một số replica trong DC từ chối/trễ ACK**.

### 7.2. Ba datacenter RF=3+3+3

Nếu keyspace có RF=3 ở ba DC, `RF_total = 9` và `QUORUM = 5`. Khi một DC mất hoàn toàn nhưng hai DC còn lại khỏe, về số lượng vẫn có tối đa 6 ACK, nên **`QUORUM` có thể đạt**.

Ngược lại `EACH_QUORUM` cần quorum **ở cả ba DC**. Nếu một DC hoàn toàn không trả ACK, **không thể đạt `EACH_QUORUM`**.

Kết luận quan trọng: mức chịu lỗi của `QUORUM` khi mất cả DC còn phụ thuộc **số DC và phân bố RF**; không thể khẳng định một cách chung chung rằng QUORUM luôn chịu được hoặc luôn thất bại khi mất một datacenter.

### 7.3. Đánh đổi latency và WAN

- `EACH_QUORUM` buộc đường ghi đợi đủ replica ở mỗi DC, do đó **độ trễ WAN, link liên DC và sức khỏe DC chậm nhất** có thể chi phối latency.
- `QUORUM` có thể cũng cần phản hồi liên DC, nhưng không buộc quorum riêng trong mọi DC.
- `LOCAL_QUORUM` thường giúp cô lập request khỏi sự cố DC xa ở mức điều kiện ACK, nhưng không tự bảo đảm dữ liệu đã đồng bộ xuyên DC tại thời điểm trả về.

Không được nói `QUORUM` **luôn** phải chờ WAN trong mọi cấu hình: nếu một DC có đủ số replica đáp ứng quorum tổng, nó có thể hoàn tất bằng ACK trong DC đó. Hãy tính RF, placement và thực tế request trước khi suy ra latency.

## 8. Tính nhất quán giữa đọc và ghi: điều kiện giao quorum

### 8.1. Quy tắc giao tập replica

Một cách tư duy thường dùng là:

~~~text
Nếu W + R > RF của cùng phạm vi replica
thì tập replica ghi đã xác nhận và tập replica đọc
phải có ít nhất một replica giao nhau
(khi topology và replica set ổn định).
~~~

Ở đây `W` và `R` là số replica tham gia xác nhận trong **cùng một tập replica phù hợp**. Quy tắc về giao tập giúp phân tích khả năng đọc thấy mutation mới, nhưng **không biến Cassandra thành hệ thống giao dịch tuần tự hóa**. Timestamp, các write cạnh tranh, clock skew, timeout, tình trạng node và đặc tính LWT vẫn ảnh hưởng tới kết quả.

Ví dụ RF tổng=6, `QUORUM` write và `QUORUM` read đều cần 4; `4 + 4 > 6` nên các tập quorum phải giao nhau.

### 8.2. Vì sao `QUORUM` write không bảo đảm `LOCAL_QUORUM` read ở mọi DC thấy ngay?

Vẫn với RF Hà Nội=3 và Singapore=3:

1. Một write `QUORUM` có thể được ACK bởi **3 replica Hà Nội + 1 replica Singapore**.
2. Một read `LOCAL_QUORUM` tại Singapore có thể lấy ACK/dữ liệu từ **hai replica Singapore chưa nhận mutation đó**.
3. Do không có giao bắt buộc giữa **1 replica đã ACK trong Singapore** và **2 replica chọn để đọc**, read có thể chưa thấy bản ghi vừa ghi.

Đây là lý do không thể khẳng định `QUORUM` write toàn cluster bảo đảm mọi DC đều có local quorum dữ liệu mới.

### 8.3. `EACH_QUORUM` write và `LOCAL_QUORUM` read ở mỗi DC

Với RF=3 cho mỗi DC, một ghi `EACH_QUORUM` được ACK bởi **ít nhất hai replica trong từng DC**. Một đọc `LOCAL_QUORUM` ở DC đó cũng tham gia **ít nhất hai replica**. Vì `2 + 2 > 3`, hai tập có giao nhau **trong chính DC đó**.

Đây là thuộc tính hữu ích khi một nghiệp vụ cần local quorum read tại bất kỳ DC nào sau khi ghi được xác nhận ở mỗi DC. Tuy nhiên phải xét **các ghi đồng thời, timestamp/hòa giải, timeout và trạng thái topology**; giao quorum không tương đương một giao dịch có điều kiện.

### 8.4. Không nhầm LWT với consistency level của write thường

`QUORUM` hoặc `EACH_QUORUM` chỉ mô tả quy tắc ACK cho các thao tác tương ứng. Nếu muốn “chỉ một client được giữ chỗ” hoặc “chỉ tạo username nếu chưa có”, cần **`IF NOT EXISTS` / `IF`** và cơ chế **lightweight transaction (Paxos)**.

LWT có **serial consistency** như `SERIAL` và `LOCAL_SERIAL` cho giai đoạn đồng thuận. Chúng **không phải tên khác của `QUORUM` hay `EACH_QUORUM`**. Đặc biệt khi cạnh tranh qua nhiều DC, phạm vi serial consistency phải được thiết kế riêng. Không suy luận “EACH_QUORUM là CAS xuyên DC”.

## 9. Xử lý unavailable, timeout và retry trong môi trường đa DC

Khi CL không thể đạt được, ứng dụng có thể gặp những tình huống khác nhau:

| Kết quả | Ý nghĩa | Cách xử lý |
|---|---|---|
| Ghi thành công | Đã đáp ứng số ACK theo CL của request | Xử lý theo nghiệp vụ, vẫn giám sát replica/repair |
| `Unavailable` | Coordinator xác định không có đủ replica khả dụng để đáp ứng CL | Kiểm tra node/DC, RF, mạng và chính sách fallback |
| `WriteTimeout` | Chưa nhận đủ xác nhận trong thời hạn | **Không chắc** mutation đã được áp dụng ở bao nhiêu replica |
| `ReadTimeout` | Không đủ phản hồi hợp lệ trong thời hạn đọc | Đánh giá DC chậm, disk/network, retry với giới hạn |
| Mất kết nối phía client | Không biết server đã hoàn thành hay chưa | Đối soát kết quả, tránh retry có tác dụng phụ trùng |

Một lỗi timeout **không có nghĩa chắc chắn write chưa đi tới replica nào**. Nếu request ghi đơn giản và có tính idempotent, client có thể retry có kiểm soát theo policy. Với increment counter, thao tác không idempotent, hoặc bước nghiệp vụ có side effect ngoài Cassandra, retry mù có thể làm sai dữ liệu.

### Có nên tự hạ `EACH_QUORUM` xuống `LOCAL_QUORUM` khi remote DC lỗi?

Đó là **quyết định thay đổi yêu cầu nhất quán của nghiệp vụ**, không chỉ là thao tác chữa timeout.

- Nếu đổi từ `EACH_QUORUM` sang `LOCAL_QUORUM`, write có thể tiếp tục thành công ở DC cục bộ **nhưng không còn cam kết quorum ở mọi DC**.
- Phải đánh giá liệu dữ liệu có được phép cập nhật ở một DC trong khi DC khác bị cô lập hay không.
- Cần chiến lược khi DC hồi phục: hinted handoff, repair, xử lý xung đột timestamp, phát hiện sai lệch và chính sách ghi trong thời gian partition mạng.

Không nên cấu hình client tự động hạ CL mà không có quyết định kiến trúc, quan sát và runbook rõ ràng.

## 10. Ví dụ Java Driver 4.x

Giả sử cluster được cấu hình `NetworkTopologyStrategy` như ở phần 2 và Java app kết nối tới `dc_hanoi`. Driver cần biết **local datacenter** để chọn node/route phù hợp và để `LOCAL_QUORUM` có ý nghĩa với vị trí request.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.UUID;

try (CqlSession session = CqlSession.builder()
        .addContactPoint(new InetSocketAddress("127.0.0.1", 9042))
        .withLocalDatacenter("dc_hanoi")
        .build()) {

    PreparedStatement upsert = session.prepare(
        "INSERT INTO shop_global.order_by_id " +
        "(order_id, status, updated_at) VALUES (?, ?, ?)"
    );

    UUID orderId =
        UUID.fromString("11111111-1111-1111-1111-111111111111");

    // Yêu cầu quorum ACK ở MỖI DC cho mutation thông thường.
    BoundStatement writeEach = upsert.bind(
            orderId, "CONFIRMED", Instant.parse("2026-11-21T10:00:00Z"))
        .setConsistencyLevel(DefaultConsistencyLevel.EACH_QUORUM);

    session.execute(writeEach);

    PreparedStatement byId = session.prepare(
        "SELECT status, updated_at FROM shop_global.order_by_id " +
        "WHERE order_id = ?"
    );

    // Đọc dùng QUORUM; KHÔNG đặt EACH_QUORUM cho SELECT.
    BoundStatement readGlobal = byId.bind(orderId)
        .setConsistencyLevel(DefaultConsistencyLevel.QUORUM);

    Row row = session.execute(readGlobal).one();
    if (row != null) {
        System.out.println(row.getString("status"));
    }

    // Khi mục tiêu là đọc cục bộ, cân nhắc LOCAL_QUORUM:
    BoundStatement readLocal = byId.bind(orderId)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

    Row localRow = session.execute(readLocal).one();
}
~~~

**Lưu ý về ví dụ:** địa chỉ contact point `127.0.0.1` chỉ là minh họa; khi triển khai thật hãy cấu hình contact point, xác thực, TLS và local DC phù hợp. `DefaultConsistencyLevel.EACH_QUORUM` là **write CL** cho câu INSERT thông thường, không phải sự bảo đảm rằng SELECT tiếp theo có thể được cấu hình EACH_QUORUM.

Trong service Java, nên đặt CL tại DAO/service hoặc profile theo yêu cầu của từng API, thay vì dùng một CL cố định cho tất cả câu lệnh. Chẳng hạn:

- **Đọc thường xuyên tại DC gần người dùng:** chọn `LOCAL_QUORUM` nếu yêu cầu nhất quán cho phép.
- **Ghi bắt buộc quorum ở mỗi DC:** dùng `EACH_QUORUM`, đồng thời chấp nhận latency và khả năng lỗi khi DC khác không sẵn sàng.
- **Ghi/đọc cần quorum tổng replica:** `QUORUM` khi phạm vi và tác động WAN phù hợp.

Các lựa chọn này phải dựa trên SLA, khả năng chịu outage và chiến lược repair, không chỉ dựa vào mong muốn “consistency càng cao càng tốt”.

## 11. Giám sát và vận hành khi dùng `QUORUM` / `EACH_QUORUM`

### 11.1. Theo dõi từng DC

Một dashboard hữu ích cần phân biệt:

| Nhóm | Cần theo dõi | Vì sao |
|---|---|---|
| Replica availability | Node UP/DOWN theo DC/rack, RF thực tế | Tính có đủ ACK để đạt CL không |
| Request metrics | Read/write latency p50/p95/p99 theo CL, timeout, unavailable | Xác định mức độ ảnh hưởng của quorum liên DC |
| Liên kết DC | RTT, packet loss, throughput, lỗi kết nối | Phát hiện WAN đang quyết định thời gian phản hồi |
| Hạ tầng | Disk latency, compaction, CPU, GC, dropped messages | Một DC chậm có thể giữ toàn bộ ghi EACH_QUORUM |
| Đồng bộ bản sao | Hinted handoff, repair, streaming | Xử lý các replica chưa nhận mutation ngoài ACK cần thiết |
| Data correctness | Xung đột trạng thái/timestamp, phiên bản dữ liệu | Quorum không thay quy tắc nghiệp vụ và CAS |

Không chỉ theo dõi coordinator ở DC ứng dụng. Một DC từ xa bị nghẽn ổ đĩa có thể khiến `EACH_QUORUM` write chậm hoặc thất bại, dù CPU và network ở DC gần client đều bình thường.

### 11.2. Các lệnh hỗ trợ điều tra

~~~bash
# Kiểm tra trạng thái node theo datacenter/rack.
nodetool status

# Thông tin topology/cluster nhìn từ node đang kiểm tra.
nodetool describecluster

# Kiểm tra tải, GC/disk/compaction theo phạm vi vận hành.
nodetool info
nodetool compactionstats

# Kiểm tra streaming nếu có phục hồi hoặc topology change.
nodetool netstats
~~~

Trong `cqlsh`, có thể kiểm tra cấu hình keyspace và mức CL hiện tại:

~~~cql
DESCRIBE KEYSPACE shop_global;
CONSISTENCY;
~~~

Khi phân tích yêu cầu thực, hãy thu thập **CQL, consistency level, keyspace, partition key, RF theo từng DC, thời điểm xảy ra lỗi và trạng thái replica**. Đừng chỉ dựa vào câu “cluster có đủ sáu node UP” mà bỏ qua phân bố ACK thực tế.

## 12. Các tình huống thiết kế thường gặp

### 12.1. API địa phương ưu tiên độ trễ và chịu sự cố WAN

Hệ thống có ứng dụng ở Hà Nội và Singapore, dữ liệu được sao chép qua hai DC. Nếu sản phẩm chấp nhận độ trễ hội tụ liên DC, `LOCAL_QUORUM` cho đọc/ghi ở DC gần ứng dụng giúp giảm phụ thuộc vào WAN trong đường xác nhận. Nhưng hai DC có thể thấy trạng thái tạm thời khác nhau, nhất là khi các bên cùng ghi vào một đối tượng.

### 12.2. Giao dịch nghiệp vụ yêu cầu cả hai DC có quorum ở thời điểm chấp nhận ghi

Nếu yêu cầu là **mutation được xác nhận tại đa số replica của từng DC trước khi trả thành công**, `EACH_QUORUM` cho ghi thông thường là ứng viên phù hợp. Cần dự trù rằng một DC mất quorum sẽ làm yêu cầu thất bại, và WAN chậm ảnh hưởng p99.

Mức này **không** giải quyết ràng buộc đồng thời kiểu “chỉ được tạo một đơn duy nhất” hoặc “số dư không âm”; các bất biến đó cần model dữ liệu và CAS/LWT hoặc một cơ chế điều phối phù hợp.

### 12.3. Muốn global quorum nhưng vẫn chịu mất một DC

Trong ba DC có RF=3 mỗi nơi, `QUORUM` toàn RF=9 cần năm ACK. Nếu mất một DC, hai DC còn lại có tối đa sáu nên có thể đáp ứng. `EACH_QUORUM` không thể đáp ứng vì đòi quorum của DC đã mất. Tuy nhiên nếu ứng dụng sau đó đọc `LOCAL_QUORUM` ở DC từng mất kết nối khi nó hồi phục, cần tính lại bảo đảm giao quorum và repair.

### 12.4. Cơ sở dữ liệu có RF không đều

Nếu RF là `5 + 1`, `QUORUM` tổng là 4; một DC RF=5 có thể tự cung cấp đủ bốn ACK. Điều đó **không tương đương đã ghi xong ở DC RF=1**. Với `EACH_QUORUM`, DC RF=1 phải có ít nhất một ACK bên cạnh quorum của DC RF=5.

Vì vậy hãy tránh cụm từ “QUORUM tự động nhân bản đồng bộ đến mọi vùng địa lý”; đó không phải định nghĩa của CL này.

## 13. Bài tập tự kiểm tra

**Bài 1.** RF Hà Nội=3, Singapore=3. Write nhận ba ACK Hà Nội và một ACK Singapore. Mức nào đạt: `QUORUM`, `EACH_QUORUM` hay `LOCAL_QUORUM` tại Hà Nội?

**Đáp án:** `QUORUM` đạt 4/6; `LOCAL_QUORUM` tại Hà Nội đạt 3/3 (vượt ngưỡng 2); `EACH_QUORUM` không đạt vì Singapore cần 2 ACK.

**Bài 2.** RF Hà Nội=3, Singapore=2. Cần bao nhiêu ACK để đạt `QUORUM` và `EACH_QUORUM`?

**Đáp án:** `QUORUM` cần tổng 3/5. `EACH_QUORUM` cần Hà Nội 2/3 **và** Singapore 2/2, tổng ít nhất bốn ACK.

**Bài 3.** Đặt `CONSISTENCY EACH_QUORUM` rồi gửi `SELECT` có đúng cách chọn read CL không?

**Đáp án:** Không. `EACH_QUORUM` không được hỗ trợ cho read thông thường. Với SELECT, cân nhắc `QUORUM` hoặc `LOCAL_QUORUM` tùy yêu cầu.

**Bài 4.** Hai DC RF=3+3. Một DC mất hoàn toàn. `QUORUM` write có thể thành công với ba replica khỏe của DC còn lại không?

**Đáp án:** Không: cần bốn ACK trên sáu replica. `LOCAL_QUORUM` tại DC còn sống có thể tiếp tục hoạt động nếu đạt 2/3 và các yếu tố khác cho phép.

**Bài 5.** Ba DC mỗi DC RF=3. Một DC down hoàn toàn. So sánh `QUORUM` và `EACH_QUORUM` write.

**Đáp án:** `QUORUM` cần năm ACK trên chín; sáu replica ở hai DC còn lại có thể đáp ứng. `EACH_QUORUM` không thể đạt vì DC down không có ACK.

**Bài 6.** Vì sao một write `QUORUM` 3+1 trong mô hình RF=3+3 không bảo đảm đọc `LOCAL_QUORUM` tại DC có một ACK sẽ thấy bản ghi mới ngay?

**Đáp án:** Hai replica được dùng cho local read tại DC đó có thể là hai replica chưa xác nhận write, nên không có giao tập replica bắt buộc trong DC ấy.

**Bài 7.** Sau một timeout của `EACH_QUORUM` write, đội vận hành muốn tự đổi sang `LOCAL_QUORUM` và retry. Có phải chỉ là giảm latency?

**Đáp án:** Không. Việc đó thay đổi bảo đảm về phạm vi xác nhận, và lần write cũ cũng có thể đã được áp dụng ở một số replica. Cần thiết kế idempotency, xác minh kết quả và có quyết định nghiệp vụ/runbook rõ ràng.

## 14. Tóm tắt nguyên tắc vận hành

1. **Đếm quorum theo đúng phạm vi:** `QUORUM` tính trên RF tổng của keyspace; `EACH_QUORUM` yêu cầu quorum tại **mỗi DC**; `LOCAL_QUORUM` chỉ xét DC cục bộ.
2. **Tôn trọng hỗ trợ thao tác:** `QUORUM` dùng được cho đọc/ghi thông thường; `EACH_QUORUM` là mức **ghi**, không dùng cho `SELECT`.
3. **Không nhầm tổng số ACK với phân bố:** `3+1` có thể đạt tổng `QUORUM=4` nhưng không đạt `EACH_QUORUM=2+2`.
4. **Cân nhắc WAN và availability:** yêu cầu quorum mỗi DC tăng phụ thuộc vào sức khỏe từng DC; local quorum giúp tách đường request khỏi remote DC nhưng không xác nhận remote đã đồng bộ.
5. **Tách nhất quán replica khỏi bất biến nghiệp vụ:** CL không tạo transaction/CAS; thao tác `IF` dùng LWT và serial consistency riêng.
6. **Không che giấu timeout bằng fallback CL tự động:** một lần timeout có kết quả chưa chắc chắn; retry cần kiểm soát.
7. **Đo theo datacenter:** replication, health, read/write latency, network, hinted handoff và repair phải được giám sát đồng thời.

**Kết luận:** Trong Apache Cassandra đa datacenter, quyết định giữa `QUORUM` và `EACH_QUORUM` không phải chọn một con số “mạnh hơn”, mà là chọn **phạm vi mà ứng dụng cần đủ bản sao xác nhận**. Hãy bắt đầu bằng RF của từng DC, loại thao tác CQL có được hỗ trợ, khả năng chịu sự cố WAN và yêu cầu quan sát dữ liệu tại mỗi vùng; sau đó mới đặt CL tương ứng trong CQL hoặc Java Driver.
