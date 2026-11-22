# Đặt bản sao theo miền lỗi và kiểm chứng khả năng chịu mất nút

Trong Apache Cassandra, việc có nhiều bản sao (replica) chỉ hữu ích cho tính sẵn sàng khi các bản sao không cùng phụ thuộc vào một điểm có thể hỏng. Chủ đề này thuộc chương **Token và sao chép**: từ token của khóa phân vùng, Cassandra xác định những nút giữ dữ liệu, rồi chiến lược replication quyết định cách phân bố các bản sao trong các **data center (DC)** và **rack**. Bài học tập trung vào cách cấu hình và kiểm chứng bố trí replica theo miền lỗi, kiểm thử khi mất nút hoặc rack, và giải thích chính xác giới hạn của từng mức nhất quán đọc/ghi.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt token, replica, replication factor (RF), data center, rack và miền lỗi; xác định vì sao RF đủ lớn vẫn có thể không chịu được mất cả một miền lỗi.
2. Thiết kế topology Cassandra bằng **NetworkTopologyStrategy**, chọn RF theo từng DC và phân chia nút vào các rack tương ứng với miền lỗi thực tế.
3. Tính số replica cần phản hồi ở **ONE**, **LOCAL_QUORUM**, **QUORUM** và **EACH_QUORUM**, rồi dự báo ứng dụng còn đọc/ghi được trong từng kịch bản.
4. Dùng CQL và công cụ vận hành để xác nhận replica của **một partition cụ thể** trước khi thử dừng nút.
5. Chạy kiểm thử có kiểm soát, ghi nhận kết quả, khôi phục nút và đánh giá việc đồng bộ dữ liệu sau sự cố.

## 2. Token, replica và miền lỗi khác nhau thế nào?

Ví dụ bảng sự kiện truy vấn theo khách hàng có khóa phân vùng là **customer_id**. Cassandra băm giá trị khóa phân vùng thành token. Token quyết định vị trí partition trên vòng token; từ vị trí đó, **replication strategy** chọn tập nút giữ các replica. Với **virtual nodes (vnodes)**, một nút có thể sở hữu nhiều vùng token, vì vậy không thể nhìn thứ tự tên nút hoặc địa chỉ IP để suy ra nơi mỗi partition được lưu.

Các khái niệm cần tách bạch:

| Khái niệm | Ý nghĩa khi thiết kế chịu lỗi |
| --- | --- |
| **Partition key / token** | Xác định partition và vị trí logic trên vòng token. Hai partition thường có tập replica khác nhau. |
| **Replica** | Bản dữ liệu của partition trên một nút. RF đếm **số nút replica trong mỗi DC** khi dùng NetworkTopologyStrategy. |
| **Node** | Tiến trình Cassandra cùng tài nguyên máy chủ/VM. Một nút chết làm mất tạm thời mọi replica đặt trên nút đó. |
| **Rack** | Nhãn topology mà Cassandra dùng để phân tán replica. Có thể ánh xạ sang availability zone (AZ), tủ máy hoặc nhóm nguồn/thiết bị mạng độc lập. |
| **Data center (DC)** | Nhóm nút được Cassandra xem là một miền vận hành, thường cùng vùng địa lý hoặc cụm mạng. |
| **Miền lỗi (fault domain)** | Tập thành phần có thể cùng hỏng vì một nguyên nhân: máy, nguồn điện, rack, AZ, DC hoặc đường kết nối. |

**Nhãn rack chỉ có tác dụng khi đúng với hạ tầng vật lý.** Gán ba tên rack khác nhau cho ba VM cùng chạy trên một máy vật lý không tạo ra ba miền lỗi độc lập. Ngược lại, nếu các VM trải trên ba AZ nhưng khai báo cùng một rack, Cassandra không nhận biết sự phân tán đó để ưu tiên đặt replica.

### Vì sao cần NetworkTopologyStrategy?

**NetworkTopologyStrategy (NTS)** phân phối số bản sao được khai báo cho từng DC và cố gắng chọn replica ở các rack khác nhau trong mỗi DC. Khi có đủ rack phù hợp với RF, mục tiêu là các replica của một partition được trải qua các rack. Nếu **RF lớn hơn số rack**, NTS phải đặt thêm replica vào các rack đã dùng; khi đó việc mất một rack có thể làm mất nhiều hơn một replica của cùng partition.

Không nên dùng **SimpleStrategy** để mô hình hóa hệ thống production nhiều DC/rack: cách chọn replica của chiến lược này không cung cấp cơ chế nhận biết rack/DC như NTS. Cassandra không tự phát hiện rack vật lý; cấu hình snitch và thông tin rack/DC là điều kiện tiên quyết.

## 3. Thiết kế mẫu: RF = 3 trên ba rack

Giả sử DC có sáu nút khỏe mạnh, được rải thành ba rack độc lập:

| Miền lỗi | Nút | Vai trò mong đợi với RF = 3 |
| --- | --- | --- |
| dc1 / rack-a | n01, n02 | Mỗi partition có một replica nằm ở một nút của rack-a. |
| dc1 / rack-b | n03, n04 | Mỗi partition có một replica nằm ở một nút của rack-b. |
| dc1 / rack-c | n05, n06 | Mỗi partition có một replica nằm ở một nút của rack-c. |

Với một partition minh họa, bộ replica có thể là n01, n04, n05:

~~~mermaid
flowchart TB
    client["Java/CQL client"] --> coord["Coordinator còn hoạt động"]
    coord --> ra["Replica n01 — rack-a"]
    coord --> rb["Replica n04 — rack-b"]
    coord --> rc["Replica n05 — rack-c"]
    subgraph dc1["Data center dc1"]
        ra
        rb
        rc
    end
~~~

Các tên nút trên sơ đồ **chỉ là ví dụ**. Tập replica thực tế thay đổi theo partition key, token và trạng thái topology; phải xác minh bằng công cụ trên cụm đang chạy. Một rack mất có thể đồng thời làm hỏng hai nút của rack đó, nhưng với cách phân bố trên, một partition chỉ mất **một trong ba** replica. Đây là lợi ích của việc cách ly miền lỗi.

So sánh hai bố trí:

- **Ba nút, cùng một rack, RF = 3:** chịu được mất một nút riêng lẻ đối với LOCAL_QUORUM, nhưng mất rack làm mất cả ba replica.
- **Sáu nút, ba rack, RF = 3:** nếu mỗi partition có một replica ở mỗi rack, mất một rack vẫn còn hai replica và LOCAL_QUORUM có thể tiếp tục hoạt động.

RF không tự bảo đảm số miền lỗi chịu được. Cần xem **cả bố trí replica lẫn số phản hồi mà consistency level yêu cầu**.

## 4. Tính khả năng đọc/ghi khi mất replica

Trong DC có RF = 3, **LOCAL_QUORUM** yêu cầu số replica phản hồi:

~~~text
local_quorum = floor(RF_cua_DC / 2) + 1
RF = 3  ->  LOCAL_QUORUM = 2
RF = 4  ->  LOCAL_QUORUM = 3
RF = 5  ->  LOCAL_QUORUM = 3
~~~

Đọc và ghi được tính **riêng theo consistency level của từng thao tác**:

| Mức nhất quán | Với RF = 3 trong dc1 | Ý nghĩa khi mất nút |
| --- | --- | --- |
| **ONE** | Cần 1 replica phản hồi. | Có thể tiếp tục nếu còn ít nhất 1 replica phù hợp, nhưng đọc có thể nhận dữ liệu cũ và ghi chưa được xác nhận ở đa số replica. |
| **LOCAL_QUORUM** | Cần 2 replica thuộc DC cục bộ phản hồi. | Vẫn có thể thành công khi mất 1 replica của partition trong DC đó; không thể cam kết thành công khi mất 2 replica. |
| **QUORUM** | Cần đa số replica trên **tổng RF của các DC** trong phạm vi yêu cầu. | Khác LOCAL_QUORUM ở cụm nhiều DC; không suy từ RF một DC để kết luận. |
| **EACH_QUORUM** | Với **ghi**, yêu cầu quorum ở **mỗi DC** có replica. | Chịu ảnh hưởng bởi DC không đạt quorum; không dùng như consistency level đọc thông thường. |

**Quy tắc giao nhau:** trong cùng một DC có RF = 3, ghi với LOCAL_QUORUM (W = 2) và đọc với LOCAL_QUORUM (R = 2) có **R + W = 4 > 3**, do đó tập replica phản hồi khi đọc và ghi có ít nhất một replica giao nhau trong điều kiện topology ổn định. Điều này giúp giảm nguy cơ đọc dữ liệu cũ sau một ghi đã thành công. Nó **không** biến Cassandra thành cơ sở dữ liệu giao dịch tuyến tính hóa cho mọi trường hợp: Cassandra còn có quy tắc xử lý xung đột theo timestamp, timeout, concurrent writes và các giới hạn về nhất quán trên nhiều DC.

Mức nhất quán quyết định số xác nhận cần thiết, **không quyết định vị trí replica**. Một yêu cầu chỉ thành công khi có đủ replica **đang hoạt động, có thể liên lạc và phản hồi đúng hạn**; trạng thái UP không bảo đảm thao tác sẽ không timeout.

### Bảng dự báo cho một partition ở dc1 (RF = 3)

| Sự cố liên quan đến partition | Replica còn khả dụng | LOCAL_ONE/ONE | LOCAL_QUORUM |
| --- | ---: | --- | --- |
| Không có sự cố | 3/3 | Có thể thành công | Có thể thành công |
| Mất đúng một nút replica | 2/3 | Có thể thành công | Có thể thành công |
| Mất một rack chứa đúng một replica | 2/3 | Có thể thành công | Có thể thành công |
| Mất hai nút đều là replica của partition | 1/3 | Có thể thành công | Không đủ quorum |
| Mất cả ba replica | 0/3 | Không đủ replica | Không đủ quorum |

“Có thể thành công” giả định coordinator/client còn kết nối và các replica sống phản hồi kịp. Với một partition khác, cùng hai nút hỏng có thể chỉ ảnh hưởng một hoặc không replica; vì vậy kiểm thử phải xác định **đúng các endpoint của khóa phân vùng**.

## 5. Khai báo DC/rack và tạo keyspace

Trong cụm dùng **GossipingPropertyFileSnitch**, mỗi nút cần có thông tin **dc** và **rack** tương ứng miền lỗi thực tế, thường khai báo trong tệp cấu hình **cassandra-rackdc.properties** và cấu hình snitch tương ứng. Ví dụ trên nút n01:

~~~properties
dc=dc1
rack=rack-a
prefer_local=true
~~~

Các nút thuộc rack-b/rack-c dùng tên rack tương ứng. Cách cấu hình và nơi triển khai cấu hình có thể khác khi chạy Cassandra trên Kubernetes, image đóng gói hoặc dịch vụ managed. Hãy kiểm tra snitch thực tế của môi trường trước khi thay đổi; sửa rack/DC của nút trong cụm đang vận hành là thay đổi topology cần quy trình riêng.

Sau khi các nút đã đăng ký topology đúng, tạo môi trường thực hành:

~~~sql
CREATE KEYSPACE IF NOT EXISTS lab_replica
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS lab_replica.events_by_customer (
  customer_id text,
  event_id timeuuid,
  event_type text,
  PRIMARY KEY ((customer_id), event_id)
) WITH CLUSTERING ORDER BY (event_id DESC);
~~~

Trong ví dụ này, khóa phân vùng chỉ gồm **customer_id**. Mỗi customer_id tạo một partition và có ba replica trong dc1; khóa **event_id** sắp xếp các hàng trong partition. Bảng được thiết kế để phục vụ truy vấn theo customer_id, đúng nguyên tắc **thiết kế bảng theo truy vấn** của Cassandra.

Nếu sử dụng **hai DC**, RF được khai báo **cho từng DC**:

~~~sql
-- Ví dụ phương án nhiều DC, không chạy nếu cụm thiếu dc2.
ALTER KEYSPACE lab_replica
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3,
  'dc2': 3
};
~~~

Khai báo dc1:3, dc2:3 nghĩa là có tối đa **sáu replica cho mỗi partition trên cả hai DC**, không phải RF tổng cộng bằng ba. Không đặt RF cao hơn số nút hiện hữu trong DC và tránh RF cao hơn số rack khi mục tiêu là mỗi rack chứa tối đa một replica cho mỗi partition.

**Thay đổi RF trên cụm đã có dữ liệu không đồng nghĩa mọi bản ghi cũ lập tức xuất hiện trên replica mới.** Cần có kế hoạch đồng bộ/repair phù hợp với phiên bản Cassandra, theo dõi hoàn tất dữ liệu và kiểm chứng trước khi xem thay đổi là xong. Không thực hiện lệnh ALTER trong ví dụ nhiều DC lên cụm lab chỉ có dc1.

## 6. Xác nhận vị trí replica trước khi gây lỗi

Thực hiện các bước trên **cụm thử nghiệm**, không dừng tùy tiện nút production.

**Bước 1 — Kiểm tra topology do Cassandra nhìn thấy.** Trên một nút có quyền chạy nodetool:

~~~bash
nodetool status
~~~

Quan sát mỗi DC, cột **Rack**, địa chỉ nút và trạng thái **UN** (Up/Normal). Đối chiếu danh sách DC/rack với bố trí vật lý/AZ; không suy luận rằng thấy ba rack là đã có ba nguồn điện hoặc AZ độc lập. Trên một nút cụ thể cũng có thể dùng:

~~~sql
SELECT data_center, rack FROM system.local;
~~~

Truy vấn system.local chỉ trả thông tin **nút đang kết nối**, không phải toàn bộ topology.

**Bước 2 — Ghi và đọc dữ liệu gốc** bằng cqlsh:

~~~sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO lab_replica.events_by_customer
  (customer_id, event_id, event_type)
VALUES ('cust-001', now(), 'before-failure');

SELECT customer_id, event_id, event_type
FROM lab_replica.events_by_customer
WHERE customer_id = 'cust-001';
~~~

Lưu kết quả truy vấn, thời điểm, consistency level và DC của coordinator/client. Vì event_id sinh bằng **now()**, cần lưu lại ID thật nếu muốn đối chiếu chính xác từng hàng sau thử nghiệm.

**Bước 3 — Xác định replica của partition cust-001**:

~~~bash
nodetool help getendpoints
nodetool getendpoints lab_replica events_by_customer cust-001
~~~

Ở các phiên bản có lệnh **getendpoints**, kết quả là những endpoint phụ trách partition key cho bảng. Nếu phiên bản/gói triển khai không cung cấp lệnh này hoặc có cú pháp khác, xem trợ giúp nodetool của phiên bản đang chạy và dùng công cụ truy vết replica tương đương. Ghi lại endpoint cùng DC/rack tương ứng; **đừng chọn ngẫu nhiên một nút để dừng**. Nếu bảng có partition key phức hợp, việc biểu diễn khóa cho công cụ có thể khác ví dụ khóa text đơn giản này.

**Bước 4 — Chọn nút sẽ hỏng** trong **tập replica đã ghi nhận** và ghi lại kỳ vọng: dừng một replica thì còn 2/3; dừng hai replica thì còn 1/3. Đồng thời bảo đảm cqlsh có thể kết nối qua **coordinator còn sống**; việc mất riêng coordinator đang dùng là phép thử kết nối client, không phải chỉ phép thử quorum replica.

## 7. Kịch bản kiểm chứng mất nút, mất rack

### Kịch bản A — Mất một nút replica

1. Xác nhận baseline: ba replica của cust-001 đều UN; INSERT và SELECT ở LOCAL_QUORUM thành công.
2. Trên **một endpoint replica** đã chọn, mô phỏng mất tiến trình Cassandra qua cơ chế vận hành của lab (ví dụ dừng service). Đợi cụm quan sát trạng thái **DN** (Down/Normal) trong nodetool status.
3. Từ một coordinator còn sống, giữ **CONSISTENCY LOCAL_QUORUM**, thực hiện SELECT dữ liệu đã ghi, rồi INSERT một sự kiện mới có event_type là during-one-down.
4. Đọc lại partition, đối chiếu hàng trước và sau lỗi. Dự kiến cả đọc và ghi vẫn thành công nếu hai replica còn lại phản hồi.
5. Khởi động lại nút; kiểm tra nút trở về UN, trạng thái đồng bộ và các lỗi/timeouts trong log/metrics.

Ví dụ lệnh dừng/khởi động **chỉ dành cho máy lab sử dụng systemd**:

~~~bash
sudo systemctl stop cassandra
# Chạy thao tác đọc/ghi thử từ một nút khác.
sudo systemctl start cassandra
~~~

Trên Kubernetes hay môi trường managed, thay bằng thao tác lỗi có kiểm soát tương ứng. Tránh thử trên production khi chưa có quy trình phê duyệt và khôi phục.

### Kịch bản B — Mất nguyên một rack

Chỉ áp dụng nếu lab thực sự có ba miền lỗi độc lập. Dừng **toàn bộ nút thuộc một rack**, không chỉ một nút. Trước đó xác minh mỗi partition được kiểm tra có **đúng một** replica trong rack mục tiêu. Với RF = 3 được rải trên ba rack, còn hai replica ở hai rack kia và LOCAL_QUORUM có thể tiếp tục. Nếu cả hai replica của một partition nằm chung rack vì cấu hình sai hoặc không đủ rack, kỳ vọng sẽ khác.

Kiểm tra nhiều partition key đại diện thay vì chỉ cust-001, vì tập endpoint khác nhau theo token. Khôi phục toàn bộ nút của rack, theo dõi trở lại UN và việc đồng bộ dữ liệu.

### Kịch bản C — Mất hai replica của cùng một partition

Trong lab, chọn **hai endpoint thực sự thuộc bộ replica của cust-001** rồi làm chúng không khả dụng. LOCAL_QUORUM (cần 2/3) phải **không thể được đáp ứng** cho partition này; kết quả thường là **UnavailableException**, **ReadTimeoutException** hoặc **WriteTimeoutException** tùy thời điểm phát hiện và loại thao tác.

Có thể chuyển một phép đọc thử sang **ONE** để quan sát trường hợp còn một replica trả lời, nhưng **không coi kết quả này là bằng chứng dữ liệu đã nhất quán**. Một ghi ở ONE thành công khi chỉ một replica sống có khả năng tạo ra cửa sổ thiếu bản sao và mất an toàn dữ liệu nếu nút cuối cùng hỏng trước khi các bản sao còn lại bắt kịp.

### Kịch bản D — Hai DC và mất một DC

Nếu dc1 và dc2 đều RF = 3, một yêu cầu ở **LOCAL_QUORUM trong dc1** cần hai replica của dc1; các replica ở dc2 không được cộng vào quorum cục bộ của dc1. Khi dc1 mất hoàn toàn, ứng dụng chỉ có thể chuyển sang dc2 nếu **client/driver được cấu hình định tuyến/failover phù hợp** và dc2 còn đủ replica. Việc ghi ở LOCAL_QUORUM dc1 thành công **không bảo đảm** cùng thời điểm ấy dc2 đã nhận đủ dữ liệu: phản hồi yêu cầu quorum tại dc1, còn truyền tới DC xa và xử lý lỗi có thể tiếp tục sau đó.

Nếu nghiệp vụ cần xác nhận ghi ở **mỗi DC**, cân nhắc **EACH_QUORUM cho ghi** cùng đánh đổi về độ trễ và tính sẵn sàng. Không tự động thay LOCAL_QUORUM bằng QUORUM/EACH_QUORUM cho mọi truy vấn: cần quyết định dựa trên mức chịu lỗi mong muốn, vị trí client và yêu cầu tính nhất quán.

## 8. Đo, kết luận và khôi phục đúng cách

Tạo biên bản kiểm thử cho từng **partition key** và mỗi lần thử:

| Dữ liệu cần ghi | Cách quan sát |
| --- | --- |
| Topology thực tế và RF | nodetool status, cấu hình keyspace, bảng đối chiếu rack ↔ miền lỗi vật lý |
| Endpoint replica của key | nodetool getendpoints hoặc công cụ tương ứng của phiên bản |
| Sự cố đã tạo | Nút/rack nào dừng, thời điểm dừng/khôi phục, trạng thái DN/UN |
| Consistency level | Lệnh CONSISTENCY trong cqlsh hoặc cấu hình từng statement của Java driver |
| Kết quả và độ trễ | Số lần SELECT/INSERT thành công, thời gian đáp ứng, timeout, loại exception |
| Dữ liệu sau khôi phục | Dòng ghi trước/trong lỗi, kết quả đọc sau ổn định, trạng thái repair/đồng bộ |

**Phân biệt ba loại tín hiệu lỗi:**

- **Unavailable**: coordinator biết số replica sống không đáp ứng consistency level yêu cầu.
- **Read/Write timeout**: đã thử thực hiện nhưng không nhận đủ phản hồi đúng hạn; kết quả **ghi timeout có thể không xác định** (một số replica đã nhận ghi).
- **Client connection failure**: có thể do contact point/coordinator hoặc cấu hình driver; chưa đủ cơ sở để kết luận tất cả replica đều hỏng.

Sau mỗi lần thử, khôi phục dịch vụ và kiểm tra nút đã gia nhập bình thường. **Hinted handoff** có thể giúp phát lại một số ghi khi replica tạm vắng, nhưng khả năng lưu hint có thời hạn và điều kiện; nó không thay thế **anti-entropy repair**. Đọc thành công một vài partition hoặc thấy tất cả nút UN cũng **không chứng minh mọi replica đã đồng bộ**. Với topology/replication thay đổi, mất nút lâu, hoặc cần bảo đảm hội tụ dữ liệu, thực hiện quy trình repair theo phiên bản và chính sách vận hành của cụm, theo dõi kết quả tới khi hoàn thành. Repair có chi phí I/O, CPU và mạng, cần lên lịch thích hợp.

### Liên hệ ứng dụng Java

Trong Java driver, hai yếu tố tách biệt:

1. **Local DC / routing:** cấu hình DC gần ứng dụng, contact points và chính sách kết nối để coordinator còn sống được chọn; cấu hình này không thay thế topology/rack đúng trên server.
2. **Consistency từng statement:** ví dụ với DataStax/Apache Cassandra Java Driver 4.x có thể đặt mức nhất quán rõ ràng trên một statement:

~~~java
import com.datastax.oss.driver.api.core.ConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement read = SimpleStatement.builder(
        "SELECT event_id, event_type FROM lab_replica.events_by_customer " +
        "WHERE customer_id = ?")
    .addPositionalValue("cust-001")
    .setConsistencyLevel(ConsistencyLevel.LOCAL_QUORUM)
    .build();

// session.execute(read) sau khi CqlSession đã cấu hình contact points/local DC.
~~~

Tùy phiên bản driver, API và cách cấu hình có thể khác. Log cần ghi rõ consistency, loại exception và DC/coordinator để tránh nhầm lỗi chọn coordinator với lỗi thiếu replica.

## 9. Những lỗi thiết kế thường gặp

| Nhầm lẫn | Hệ quả / cách sửa |
| --- | --- |
| “RF = 3 nghĩa là chịu được bất kỳ ba nút hỏng.” | Sai: với LOCAL_QUORUM, một partition RF = 3 chỉ còn đáp ứng quorum khi **tối đa một replica** của partition đó không khả dụng. |
| “Đã có ba bản sao nên rack nào hỏng cũng được.” | Sai nếu các bản sao cùng rack hoặc rack logic không phản ánh miền lỗi vật lý. |
| “Sáu nút trong DC, RF = 3 nghĩa là mỗi partition có sáu bản sao.” | Sai: có ba replica trong DC; sáu nút chỉ là tổng nút tham gia phân phối nhiều partition. |
| “LOCAL_QUORUM trong dc1 tính cả replica dc2.” | Sai: quorum chỉ tính replica **trong DC cục bộ** đối với LOCAL_QUORUM. |
| “nodetool status toàn UN là dữ liệu trên mọi replica giống nhau.” | Sai: UN mô tả trạng thái nút; cần kiểm chứng đồng bộ/repair và hành vi đọc ghi. |
| “Dừng hai nút bất kỳ sẽ thử được mất hai replica.” | Chưa chắc: hai nút đó có thể không cùng giữ partition đang kiểm tra. |
| “Tăng RF bằng ALTER là đã nhân bản toàn bộ dữ liệu cũ.” | Sai: phải thực hiện kế hoạch repair/đồng bộ và xác nhận kết quả. |
| “Dùng ONE để qua lỗi là không còn rủi ro.” | ONE có thể giảm yêu cầu phản hồi, nhưng tăng khả năng đọc cũ và rủi ro khi các replica chưa bắt kịp. |

## 10. Bài tập thực hành và tiêu chí hoàn thành

**Bối cảnh:** dc1 có sáu nút thuộc ba rack độc lập (hai nút/rack), NetworkTopologyStrategy với RF = 3. Bảng events_by_customer được ghi và đọc ở LOCAL_QUORUM.

1. Dùng nodetool status chứng minh cấu hình DC/rack đã thấy đúng; ghi lại một sơ đồ vị trí vật lý.
2. Tạo ba partition có khóa cust-001, cust-002, cust-003; với mỗi khóa, liệt kê ba endpoint replica và rack tương ứng. Kiểm tra xem mỗi khóa có một replica ở mỗi rack không.
3. Với cust-001, dự báo kết quả đọc/ghi khi dừng một endpoint; thử và ghi bằng chứng. Lặp lại cho việc dừng rack chứa endpoint đó (nếu lab cho phép).
4. Dự báo và thử tình huống hai endpoint của cust-001 cùng mất; so sánh LOCAL_QUORUM với phép đọc ONE chỉ mang tính quan sát.
5. Phục hồi các nút, kiểm tra lại dữ liệu ghi trước và trong sự cố; nêu quy trình đảm bảo dữ liệu đồng bộ và cách phát hiện timeout hoặc replica chưa bắt kịp.

**Đạt yêu cầu** khi biên bản trả lời được ba câu: (a) **Partition nào nằm trên những nút/rack nào?** (b) **Với sự cố cụ thể, bao nhiêu replica còn phản hồi so với consistency level?** (c) **Có bằng chứng nào xác nhận hệ thống đã trở về trạng thái khỏe mạnh và dữ liệu được đồng bộ sau sự cố?**

### Câu hỏi tự kiểm tra

- Vì sao cùng RF = 3 nhưng bố trí ba rack có thể sống sót khi mất một rack, trong khi bố trí một rack thì không?
- Với RF = 4 trên ba rack, tại sao mất một rack có thể khiến LOCAL_QUORUM không đạt yêu cầu?
- Vì sao phép thử “dừng hai nút” không đủ để kết luận một partition mất hai replica?
- Vì sao ghi LOCAL_QUORUM ở dc1 không đảm bảo một lệnh đọc LOCAL_QUORUM ngay lập tức tại dc2 luôn thấy bản ghi mới nếu có sự cố truyền liên DC?

Ý chính cần giữ: **khả năng chịu lỗi là thuộc tính của từng partition, bộ replica thực tế, miền lỗi vật lý và consistency level được dùng tại thời điểm yêu cầu**. Thiết kế đúng cần đi kèm phép thử có đo đạc; replication bảo vệ tính sẵn sàng khi đủ replica còn sống, còn repair và quy trình khôi phục bảo vệ tính hội tụ dữ liệu sau khi nút trở lại.
