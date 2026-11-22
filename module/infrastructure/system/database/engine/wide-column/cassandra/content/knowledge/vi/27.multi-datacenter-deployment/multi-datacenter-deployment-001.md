# Thiết kế datacenter/rack theo miền lỗi thực tế trong Apache Cassandra

## 1. Bắt đầu từ miền lỗi, không bắt đầu từ tên datacenter

Apache Cassandra là cơ sở dữ liệu **wide-column phân tán**: dữ liệu được phân vùng theo **partition key**, sao chép lên nhiều **replica** và có thể phục vụ truy vấn CQL từ ứng dụng Java tại nhiều địa điểm. Để hệ thống tiếp tục phục vụ khi xảy ra sự cố, các replica phải được đặt tại những vị trí **không cùng thất bại vì một nguyên nhân**.

**Miền lỗi (failure domain)** là phạm vi tài nguyên có thể ngừng hoạt động đồng thời do một sự cố chung. Ví dụ:

- Một máy chủ hỏng → các tiến trình trên máy đó cùng mất.
- Một rack dùng chung nguồn hoặc switch ToR (*top-of-rack*) gặp sự cố → nhiều máy trong rack mất kết nối.
- Một availability zone (AZ) mất điện, mạng hoặc storage → nhiều rack/VM trong zone có thể cùng bị ảnh hưởng.
- Một datacenter, khu vực địa lý hoặc tuyến WAN gặp sự cố → các node của cả khu vực có thể không còn kết nối.

Trong Cassandra, hai nhãn topology quan trọng là **datacenter (DC)** và **rack**. Chúng không tự tạo khả năng chống chịu lỗi: Cassandra chỉ biết nhãn do bạn khai báo qua **snitch**. Nếu đặt cả ba replica trong cùng một zone vật lý nhưng khai thành ba rack khác nhau, thuật toán placement vẫn có thể nghĩ chúng độc lập dù thực tế cùng mất khi zone hỏng.

**Nguyên tắc thiết kế:** ánh xạ topology Cassandra vào những miền lỗi có ý nghĩa của hạ tầng đang dùng, sau đó kiểm tra xem số replica và consistency level còn đáp ứng được khi *một miền lỗi thực sự biến mất* hay không.

## 2. Ba lớp cần tách biệt: node, rack và datacenter

| Lớp | Cassandra nhìn thấy gì? | Miền lỗi thực tế nên phản ánh | Ví dụ |
| --- | --- | --- | --- |
| **Node** | Một Cassandra instance có host ID, địa chỉ và token ownership | Máy/VM độc lập | VM `cassandra-a1` |
| **Rack** | Nhóm node có cùng rack label trong một DC | Tủ rack, nguồn/switch độc lập hoặc AZ tùy hạ tầng | `rack=az-a` |
| **Datacenter** | Nhóm node cùng DC label; replication và local CL xét theo DC | Một trung tâm dữ liệu/region hoặc nhóm AZ có độ trễ liên kết phù hợp | `dc=region-a` |

Ví dụ phổ biến trên cloud: **một region tương ứng một DC Cassandra**, và **mỗi AZ trong region tương ứng một rack Cassandra**. Đây là *cách ánh xạ tham khảo*, không phải quy tắc áp dụng cho mọi cloud.

Với hệ thống on-premises, rack có thể trùng một tủ vật lý nếu nguồn và ToR thực sự độc lập. Nhưng nếu nhiều rack dùng chung một PDU/UPS hoặc switch mạng lõi, cần đánh giá liệu nhãn rack đó có tạo sự độc lập mà ứng dụng mong muốn hay không.

### Minh họa hai DC, mỗi DC ba rack

```text
                       CỤM CASSANDRA
               NetworkTopologyStrategy (RF: 3 + 3)

        DC region-a                        DC region-b
   +----------------------+           +----------------------+
   | rack az-a1: Node A1 |           | rack az-b1: Node B1 |
   | rack az-a2: Node A2 |           | rack az-b2: Node B2 |
   | rack az-a3: Node A3 |           | rack az-b3: Node B3 |
   +----------------------+           +----------------------+
       mạng nội vùng                         mạng nội vùng
                 <-------- WAN -------->

    Trong mỗi DC: 3 replica của một partition được ưu tiên
    đặt trên các rack khác nhau khi topology cho phép.
```

Sơ đồ chỉ minh họa **một partition** với RF = 3 tại mỗi DC. Một cluster thực tế có thể có nhiều node trong mỗi rack, nhiều token range và các keyspace có RF khác nhau.

## 3. Phân biệt mục tiêu chịu lỗi node, rack và DC

Trước khi tạo cluster, chuyển yêu cầu nghiệp vụ thành kịch bản mất tài nguyên cụ thể.

| Kịch bản | Điều kiện thiết kế cần xem | Kết quả mong đợi |
| --- | --- | --- |
| Hỏng một node | Số replica còn lại, CL, sức chứa dự phòng | Đọc/ghi vẫn đạt CL |
| Mất một rack/AZ | Các replica có thực sự ở những rack độc lập? | Mất một rack không mất toàn bộ bản sao |
| Mất cả DC | DC còn lại có RF và số node đủ không? Ứng dụng có chuyển vùng được không? | Có thể phục vụ tại DC khác theo chính sách đã chuẩn bị |
| WAN giữa hai DC bị chia cắt | CL là local hay global? Ứng dụng ghi ở một hay cả hai DC? | Không ngầm giả định hai bên luôn thấy dữ liệu mới nhất |
| Mất mạng dùng chung cho cả hai DC | Các DC có thật sự có tuyến mạng độc lập? | Có kế hoạch giảm sự cố tương quan |

**RTO** (*recovery time objective*) là thời gian phục hồi dịch vụ mục tiêu; **RPO** (*recovery point objective*) là mức mất mát dữ liệu chấp nhận được. Có nhiều replica không tự đưa RTO/RPO về 0: còn phụ thuộc commit log, đồng bộ giữa DC, CL, lỗi đồng thời, backup và cơ chế điều phối chuyển vùng của ứng dụng.

### Phân tán replica không thay cho năng lực dự phòng

Giả sử một DC có ba rack, mỗi rack một node và RF = 3. Khi mất một rack, hai node còn lại có thể đủ cho `LOCAL_QUORUM`. Tuy nhiên, chúng phải gánh thêm tải CQL, compaction và repair. Nếu trước sự cố mỗi node đã chạy gần giới hạn CPU/đĩa, **quorum vẫn có thể tồn tại về mặt số lượng nhưng latency/timeout vượt SLA**.

Thiết kế cần đồng thời đáp ứng:

1. **Replica placement:** còn đủ bản sao.
2. **Quorum availability:** còn đủ phản hồi theo CL.
3. **Capacity headroom:** những node còn lại phục vụ được lưu lượng đỉnh.
4. **Operational recovery:** có runbook khôi phục/repair sau sự cố.

## 4. Chọn replication bằng NetworkTopologyStrategy

Với nhiều DC, chiến lược tiêu chuẩn để chỉ định RF theo từng DC là `NetworkTopologyStrategy` (NTS). Ví dụ dùng hai DC tên `region_a` và `region_b`, mỗi DC có ít nhất ba node đặt ở các miền lỗi phù hợp:

```sql
CREATE KEYSPACE IF NOT EXISTS orders_global
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'region_a': 3,
    'region_b': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS orders_global.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id text,
    state text,
    updated_at timestamp
);
```

Tính chất cần nhớ:

- `RF = 3` tại `region_a` có nghĩa **ba replica cho mỗi partition trong DC đó**, không phải mỗi node lưu cả bảng theo một bản sao hoàn chỉnh.
- `RF = 3` tại `region_b` là **ba bản sao khác**, do những node ở DC đó lưu.
- Cassandra cố gắng đặt replica trên **rack khác nhau** trong phạm vi DC khi topology và số rack khả dụng cho phép. Nếu có ít rack hơn RF, nhiều replica có thể cùng rack.
- Các tên DC trong CQL phải khớp **chính xác** với tên DC mà snitch báo cho các node.
- Việc sửa RF trong schema **không tự đồng bộ ngay dữ liệu còn thiếu trên tất cả node**; thay đổi replication đòi hỏi quy trình streaming/rebuild/repair phù hợp phiên bản.

Với cluster production nhiều DC, không nên dùng `SimpleStrategy` như một cách thay thế NTS. `SimpleStrategy` không mô hình hóa sự phân phối bản sao theo DC/rack cho mục tiêu chịu lỗi nhiều vùng.

### RF phải được đánh giá cùng số rack

| Cấu hình trong một DC | Tình huống mất một rack | Nhận xét |
| --- | --- | --- |
| RF 3, ba rack độc lập, replica trải trên ba rack | Có thể còn hai replica | Có cơ sở phục vụ `LOCAL_QUORUM = 2` nếu các node còn lại khỏe |
| RF 3, chỉ hai rack | Có rack có thể chứa nhiều replica | Mất rack chứa hai replica có thể khiến quorum không đạt |
| RF 3, ba rack khai báo nhưng cùng chung nguồn/mạng vật lý | Cùng nguồn/mạng lỗi có thể làm mất cả ba | Tên rack không bảo vệ được lỗi tương quan |
| RF 2, hai rack | Mất một rack còn một replica | `LOCAL_QUORUM = 2` không còn đạt |
| RF 3, ba rack nhưng một rack có nhiều partition nóng | Replica có thể phân bố đúng nhưng tải không cân | Cần đánh giá hot partition, token và capacity, không chỉ số rack |

Việc chọn RF ảnh hưởng chi phí lưu trữ, băng thông ghi, repair và khả năng chịu lỗi. RF cao hơn không thay thế việc thiết kế đúng miền lỗi và giữ dung lượng dự phòng.

## 5. Kiểm tra consistency level qua các miền lỗi

Giả sử cả hai DC đều có RF = 3. Tổng số bản sao của một partition là 6.

| Consistency level | Số phản hồi cần trong ví dụ | Điều xảy ra nếu toàn bộ `region_a` mất |
| --- | --- | --- |
| `LOCAL_ONE` tại `region_b` | 1 replica của `region_b` | Có thể phục vụ nếu còn một replica khỏe |
| `LOCAL_QUORUM` tại `region_b` | 2 trong 3 replica `region_b` | Có thể phục vụ nếu còn đủ hai replica khỏe |
| `QUORUM` (toàn cluster) | 4 trong tổng 6 replica | Không thể đạt nếu chỉ còn 3 replica của `region_b` |
| `EACH_QUORUM` (cho ghi thông thường) | Quorum ở **mỗi DC**, tức 2 + 2 | Không thể đạt vì `region_a` không phản hồi |
| `ALL` | Cả 6 replica | Không thể đạt |

**Lưu ý về `EACH_QUORUM`:** đây là CL dùng cho ghi, không phải một lựa chọn đọc thông thường tương đương `LOCAL_QUORUM`.

Với `LOCAL_QUORUM`, phản hồi của một DC được tính độc lập. Nó giảm phụ thuộc WAN trên đường xác nhận của client, nhưng **không chứng minh mọi DC đã ghi/đọc cùng phiên bản tại thời điểm đó**.

### Khi WAN bị gián đoạn, điều gì được bảo đảm?

Ví dụ ứng dụng tại `region_a` ghi một mutation ở `LOCAL_QUORUM`:

1. Coordinator gửi mutation theo placement tới các replica tương ứng; việc phân phối có thể bao gồm DC còn lại.
2. Ứng dụng có thể nhận thành công sau khi đủ replica **trong region_a** xác nhận.
3. Nếu WAN đang lỗi, replica tại `region_b` có thể chưa có mutation mới.
4. Ứng dụng tại `region_b` đọc `LOCAL_QUORUM` có thể vẫn thấy giá trị cũ.
5. Sau khi mạng phục hồi, cần xét hinted handoff và **anti-entropy repair** để bảo đảm dữ liệu hội tụ, nhất là khi sự cố kéo dài.

Đây không phải một mô hình **multi-region linearizable database** chỉ vì dùng hai DC. Với nghiệp vụ đòi xác nhận đồng bộ toàn cầu, phải phân tích CL, độ trễ WAN, khả năng sẵn sàng và loại thao tác; không tự nâng mọi request lên `EACH_QUORUM` mà không đo tác động.

### Công thức quorum chỉ đúng trong phạm vi xác định

Với RF = 3 trong một DC:

```text
LOCAL_QUORUM = floor(3/2) + 1 = 2

Hai quorum bất kỳ trong CÙNG tập ba replica phải giao nhau.
Hai local quorum thuộc HAI DC KHÁC NHAU không bắt buộc giao nhau.
```

Cần phân biệt **giao nhau của quorum** với **khả năng chịu lỗi vật lý**. Nếu các replica thuộc cùng miền lỗi thực tế, nhiều replica có thể mất cùng lúc khiến phép đếm quorum chỉ còn giá trị lý thuyết.

## 6. Ánh xạ rack từ hạ tầng thực vào snitch

Snitch là cách Cassandra biết mỗi node đang ở **DC/rack** nào. Với `GossipingPropertyFileSnitch`, thông tin DC/rack thường được cấu hình qua file `cassandra-rackdc.properties` trên từng node.

Ví dụ trên node A1 ở zone `az-a1`:

```properties
dc=region_a
rack=az-a1
```

Ví dụ trên node A2 ở zone `az-a2`:

```properties
dc=region_a
rack=az-a2
```

Ví dụ trên node B1 tại vùng khác:

```properties
dc=region_b
rack=az-b1
```

Trong các triển khai sử dụng `cassandra.yaml`, snitch tương ứng được chọn bằng cấu hình ví dụ:

```yaml
endpoint_snitch: GossipingPropertyFileSnitch
```

Các đoạn trên **chỉ minh họa giá trị**, không phải bộ cấu hình khởi chạy đầy đủ. Các tham số và cách triển khai có thể khác trên Cassandra 3.x/4.x/5.x hoặc nền tảng quản lý cluster; một số hệ thống dùng snitch hoặc operator tự gán topology.

### Tên logic phải khớp sự thật vật lý

| Nhãn logic | Cách triển khai tốt | Cách triển khai nguy hiểm |
| --- | --- | --- |
| `dc=region_a` | Các node thuộc vùng có latency/điều phối vận hành tương ứng | Trộn những máy cách xa qua WAN vào một DC mà không đánh giá CL |
| `rack=az-a1` | Những node cùng AZ, khác AZ được gán rack khác | Gán ba rack khác nhau cho ba VM đều nằm ở một AZ |
| `rack=rack-01` on-prem | Phản ánh nguồn, ToR và khả năng cách ly thực tế | Nhiều rack “khác” nhưng dùng cùng điểm lỗi mạng/điện |
| `dc=region_b` | RF và tính sẵn sàng của region_b được quản lý độc lập | Đặt node ở region_b nhưng khai dc region_a để khỏi sửa keyspace |

**Không sửa DC/rack của node đang hoạt động rồi chỉ restart** như một cách “đổi chỗ replica”. Cassandra dùng topology để xác định placement; thay nhãn có thể làm thay đổi replica sets, ảnh hưởng đọc/ghi và yêu cầu di chuyển dữ liệu. Phải dùng quy trình thay đổi topology được phiên bản/đơn vị vận hành hỗ trợ.

## 7. Các anti-pattern hay làm hỏng thiết kế miền lỗi

### 7.1. Mỗi node một rack, nhưng tất cả chạy cùng zone

Cassandra nhìn thấy nhiều rack và tưởng có thể đặt replica độc lập; nhưng zone bị mất thì tất cả biến mất. Thêm nhãn không tạo ra nguồn điện hoặc đường mạng mới.

### 7.2. Dùng một DC trải trên mạng WAN có độ trễ cao

Nếu node trong cùng DC cách nhau qua kết nối nhiều chục hoặc hàng trăm mili giây, `LOCAL_QUORUM` có thể phải chờ WAN để lấy hai xác nhận. Kết quả là latency local không còn “local” và phụ thuộc vào sự ổn định của tuyến liên vùng.

### 7.3. Tạo DC mới nhưng quên keyspace replication

Nếu keyspace chỉ khai báo `region_a: 3`, các node tại `region_b` có thể gia nhập cluster mà không trở thành replica của keyspace đó. Ứng dụng tại vùng mới không tự có ba bản sao của dữ liệu cần dùng chỉ vì có node mới.

### 7.4. Ba replica cùng chia sẻ một tài nguyên không dự phòng

Có thể ba VM nằm trên các host khác nhau nhưng cùng storage appliance, top-of-rack uplink hoặc một chính sách network phụ thuộc chung. Khi điểm chung hỏng, RF = 3 vẫn mất hiệu quả chịu lỗi.

### 7.5. Chỉ kiểm tra trạng thái node “UN”

`nodetool status` báo Up/Normal là tín hiệu membership, **không bảo đảm** replication đã đầy đủ, DC/rack đúng, repair đang theo kịp hoặc Java Driver có thể tiếp cận CQL endpoint từ vùng khác.

### 7.6. Cho rằng driver tự failover qua DC khác

Java Driver thường định tuyến theo **local datacenter** đã cấu hình. Việc chuyển ứng dụng sang DC khác khi cả DC bị lỗi cần thiết kế trước: kết nối, routing, DNS/service discovery, xác thực, cấu hình local DC mới và chấp nhận khả năng dữ liệu chưa hội tụ. Không thể dựa vào việc driver tự động dùng remote DC trong mọi tình huống.

## 8. Phân bổ node và tính toán khả năng chịu lỗi

Một thiết kế thử nghiệm có hai region, mỗi region ba AZ, mỗi AZ một node:

| DC | Rack/AZ | Node minh họa | Số bản sao mục tiêu cho mỗi partition |
| --- | --- | --- | --- |
| `region_a` | `az-a1` | A1 | 1 tại AZ này khi RF3 được phân tán đều |
| `region_a` | `az-a2` | A2 | 1 tại AZ này khi RF3 được phân tán đều |
| `region_a` | `az-a3` | A3 | 1 tại AZ này khi RF3 được phân tán đều |
| `region_b` | `az-b1` | B1 | 1 tại AZ này khi RF3 được phân tán đều |
| `region_b` | `az-b2` | B2 | 1 tại AZ này khi RF3 được phân tán đều |
| `region_b` | `az-b3` | B3 | 1 tại AZ này khi RF3 được phân tán đều |

Với giả định lý tưởng trên:

- Mất A1: region_a còn A2 và A3, có thể đáp ứng `LOCAL_QUORUM` của region_a.
- Mất toàn bộ region_a: client chuyển sang region_b **nếu có khả năng chuyển vùng đã chuẩn bị**; region_b còn ba replica, đủ `LOCAL_QUORUM` địa phương.
- Đứt WAN: mỗi region vẫn có thể phục vụ local quorum trên dữ liệu nó đang giữ, **nhưng có thể khác nhau về độ mới của dữ liệu**.
- Mất hai AZ trong cùng region: region đó chỉ còn một replica, không đủ `LOCAL_QUORUM` RF3.

Với production, không nên tính capacity bằng “ba node vừa đủ cho ba AZ” mà bỏ qua tình huống một AZ đã mất và hai AZ còn lại chịu tải. Nếu ứng dụng yêu cầu uptime qua lỗi AZ, các node còn lại phải đủ I/O, CPU, RAM, dung lượng và mạng để phục vụ lưu lượng còn lại.

### Khi một rack có nhiều node

Cassandra có thể đặt nhiều partition/token khác nhau lên nhiều node trong cùng rack, miễn mỗi partition được replica placement phân tán theo rack tối đa trong khả năng topology. Không nhất thiết phải có đúng một node trên mỗi rack.

Điều quan trọng là **chống cùng lỗi** và giữ **phân bố tài nguyên**. Nếu một rack có số node gấp nhiều lần rack khác, cluster có thể không đạt cân bằng tải lý tưởng dù NTS nhận ra ba rack. Hãy kiểm tra ownership theo keyspace, disk usage, token distribution và hotspot thực tế.

## 9. Dữ liệu, kết nối và mạng giữa hai DC

Multi-DC Cassandra có thể phải trao đổi:

1. **Mutation replication:** coordinator phân phối ghi tới replica ở các DC liên quan.
2. **Gossip/membership:** node nhận biết topology và trạng thái thành viên.
3. **Streaming:** thêm node/DC, rebuild, thay topology hoặc sửa sai khác.
4. **Repair:** validation và streaming để đối chiếu replica, có thể đi qua WAN.
5. **Client CQL:** ứng dụng thường kết nối với coordinator trong local DC; failover cần tính trước tuyến truy cập vùng khác.

Đường truyền giữa DC phải được đánh giá về băng thông, độ trễ, packet loss, firewall/TLS và khả năng độc lập trước các sự cố tương quan. Không chỉ mở cổng CQL rồi kết luận topology hoàn chỉnh; **internode communication và streaming** cũng phải khả dụng.

### Đặt ngưỡng vận hành theo tình huống mất DC

| Tài nguyên hoặc chỉ số | Trước sự cố | Trong sự cố một DC | Sau khi phục hồi |
| --- | --- | --- | --- |
| Quorum | Mỗi DC đủ replica theo RF | DC còn hoạt động phải tự đáp ứng CL đã chọn | Kiểm tra lại placement, repair |
| Read/write p95/p99 | Baseline theo DC | Tải dồn và latency có thể tăng | Đo lại sau khi stream/repair |
| Network | Mutation và gossip bình thường | Đường chuyển vùng của client có thể tăng tải | Hinted handoff, repair/stream có thể tạo burst |
| Disk | Dữ liệu tại từng replica | Tải tập trung hơn trên DC còn sống | Repair/compaction cần headroom |
| Dữ liệu | Các DC có thể tạm lệch ngắn | DC mất kết nối bỏ lỡ mutation | Phải kiểm chứng hội tụ trước khi kết luận phục hồi hoàn tất |

**Không chỉ nhìn vào số lượng node còn Up.** Một DC còn đủ quorum nhưng ổ đĩa bão hòa hoặc CQL p99 tăng đột biến vẫn có thể khiến dịch vụ vi phạm SLO.

## 10. CQL thực hành: hai keyspace với yêu cầu chịu lỗi khác nhau

Ví dụ dưới giả định cluster đã thực sự triển khai node ở `region_a` và `region_b`. Dùng topology thật và kiểm tra cấu hình trước khi chạy.

### Keyspace chỉ có replica ở một DC

```sql
CREATE KEYSPACE IF NOT EXISTS orders_local
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'region_a': 3
};
```

Ở đây, `orders_local` **không có RF cho region_b**. Việc tạo sáu node ở hai DC không tự làm dữ liệu keyspace này hiện diện ở region_b.

### Keyspace có replica ở cả hai DC

```sql
CREATE KEYSPACE IF NOT EXISTS orders_global
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'region_a': 3,
    'region_b': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS orders_global.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id text,
    state text,
    updated_at timestamp
);

INSERT INTO orders_global.orders_by_id
    (order_id, customer_id, state, updated_at)
VALUES (
    11111111-1111-4111-8111-111111111111,
    'customer-42',
    'PENDING',
    '2026-11-20 09:00:00+0000'
);

SELECT state, updated_at
FROM orders_global.orders_by_id
WHERE order_id = 11111111-1111-4111-8111-111111111111;
```

Trong `cqlsh` được kết nối tới coordinator của từng DC:

```text
CONSISTENCY LOCAL_QUORUM;
```

Thực hành đối chiếu từ hai DC **chỉ có ý nghĩa khi keyspace đã có bản sao ở cả hai vùng và đã được cung cấp dữ liệu đúng**. Nếu cluster thử chỉ có một DC hoặc ít node hơn RF, `LOCAL_QUORUM` có thể trả lỗi không đủ replica.

### Vì sao không được tùy tiện đổi RF?

Giả sử keyspace đang chạy chỉ có `region_a: 3`, sau đó thêm `region_b: 3` bằng `ALTER KEYSPACE`. Câu lệnh DDL thay **metadata replication**, không bảo đảm dữ liệu lịch sử đã ngay lập tức được stream đầy đủ sang mọi node của region_b.

Cần có runbook triển khai DC mới với công cụ **rebuild/streaming và repair** phù hợp phiên bản, theo dõi phạm vi và trạng thái hoàn tất trước khi chuyển traffic. Hãy xem `nodetool help rebuild` và tài liệu vận hành của phiên bản thực tế; không chạy ngẫu nhiên lệnh rebuild trên node production chỉ để kiểm tra.

## 11. Java Driver 4.x: chọn local datacenter đúng

Trong ứng dụng Java, `CqlSession` cần biết **local datacenter** để load-balancing policy chọn coordinator gần ứng dụng. Ví dụ Java Driver 4.x:

```java
import java.net.InetSocketAddress;
import java.util.Optional;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class RegionalOrderReader {
    private final CqlSession session;
    private final PreparedStatement selectState;

    public RegionalOrderReader(CqlSession session) {
        this.session = session;
        this.selectState = session.prepare(
            "SELECT state FROM orders_global.orders_by_id WHERE order_id = ?"
        );
    }

    public Optional<String> findState(UUID orderId) {
        BoundStatement statement = selectState.bind(orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        Row row = session.execute(statement).one();
        if (row == null || row.isNull("state")) {
            return Optional.empty();
        }
        return Optional.of(row.getString("state"));
    }

    // Ví dụ cấu hình cho ứng dụng triển khai tại region_a.
    public static CqlSession openRegionASession() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.10.0.11", 9042))
            .withLocalDatacenter("region_a")
            .build();
    }
}
```

Địa chỉ và tên vùng trong ví dụ chỉ mang tính minh họa. Trong môi trường thực phải cấu hình đầy đủ contact points dự phòng, bảo mật, chứng chỉ, credentials, network reachability và lifecycle session; **không tạo một session cho mỗi request**.

### Hai ứng dụng ở hai region

| Ứng dụng | Local DC cấu hình | CL `LOCAL_QUORUM` tham chiếu | Điều cần biết |
| --- | --- | --- | --- |
| App A chạy gần `region_a` | `region_a` | Hai replica trong `region_a` khi RF3 | Có thể không chờ xác nhận từ region_b |
| App B chạy gần `region_b` | `region_b` | Hai replica trong `region_b` khi RF3 | Có thể tạm thời nhìn thấy phiên bản khác App A |

Nếu cần chuyển App A sang `region_b` khi region_a lỗi, phải có **kế hoạch failover ứng dụng** gồm local DC mới, endpoint và lưu ý nhất quán. Không giả định `withLocalDatacenter("region_a")` tự đổi sang `region_b` khi sự cố.

## 12. Playbook kiểm tra thiết kế datacenter/rack

### Bước 1 — Vẽ bản đồ lỗi thực tế

Liệt kê từng node cùng:

- Cloud region/site, AZ, rack vật lý hoặc nhóm nguồn/switch.
- Host/VM/hypervisor, loại storage, network uplink và nguồn điện.
- DC/rack label mà Cassandra hiện nhận.
- Những tài nguyên chung có thể làm nhiều node mất đồng thời.

Đánh dấu các cặp node mà **một sự cố duy nhất** có thể đánh gục. Nếu chúng đang nằm ở những “rack” Cassandra khác nhau, cần xem lại thiết kế.

### Bước 2 — Đối chiếu topology được Cassandra thấy

Trên những node vận hành:

```bash
nodetool status
nodetool describecluster
nodetool status orders_global
```

`nodetool status` thường nhóm node theo DC; kết hợp với metadata/snitch và hệ thống quản lý hạ tầng để xác minh rack. `nodetool describecluster` giúp quan sát một số thông tin về cluster và schema version, nhưng **không phải bằng chứng đầy đủ về độc lập nguồn điện/mạng**.

Lưu ý cột `Owns (effective)` có thể phụ thuộc keyspace/RF. Với replication, tổng tỷ lệ ownership giữa các node **không nhất thiết bằng 100%** theo cách cộng đơn giản.

### Bước 3 — Kiểm tra cấu hình replication và CL

Trong `cqlsh`:

```text
DESCRIBE KEYSPACE orders_global;
CONSISTENCY LOCAL_QUORUM;
```

Đảm bảo tên DC trong NTS trùng snitch và từng DC có đủ số node/rack theo mục tiêu. Xác định CL được dùng bởi mỗi luồng nghiệp vụ, không chỉ CL mặc định của một phiên `cqlsh`.

### Bước 4 — Kiểm chứng sự cố theo kịch bản, không phá production

Trong môi trường **lab/staging cô lập**, kiểm thử:

1. Mất một node trong một rack: local quorum còn đạt không?
2. Mất một AZ/rack: có đủ bản sao và headroom?
3. Gián đoạn WAN: hai DC còn phục vụ local read/write không, dữ liệu hội tụ về sau thế nào?
4. Mất một DC: các ứng dụng có đường chuyển vùng và kết nối CQL tới DC còn lại không?
5. DC hồi phục: trạng thái streaming, hinted handoff, repair và p95/p99 có ổn định không?

Không cố tình cắt mạng, dừng nhiều node hoặc sửa topology sống trong production chỉ để mô phỏng.

### Bước 5 — Xây dựng lịch repair và mục tiêu phục hồi

Repair **nội DC** có thể đồng bộ các replica cục bộ, nhưng **không tự so sánh hai DC** nếu chúng đều nhất quán nội bộ song dữ liệu khác nhau. Nếu cần hội tụ liên DC, lịch anti-entropy repair phải bao phủ token ranges và replica phù hợp giữa những DC liên quan.

Đồng thời theo dõi:

- Thời gian replica/DC mất kết nối so với `gc_grace_seconds` và thời hạn hint.
- Sự khác biệt dữ liệu sau khi vùng mất mạng phục hồi.
- Tombstone/TTL để hạn chế nguy cơ dữ liệu đã xóa xuất hiện lại.
- Chi phí WAN, disk I/O, compaction backlog và p95/p99 lúc repair/stream.

**Read repair không thay thế anti-entropy repair** đối với partition không được đọc; compaction cũng không thay thế đồng bộ replica. Backup và kế hoạch khôi phục vẫn cần thiết ngay cả khi RF cao.

## 13. Tình huống phân tích

### Tình huống 1 — “Ba rack” nhưng cùng AZ

Ba node được gán `rack1`, `rack2`, `rack3`, đều là VM trong AZ-a. Keyspace có RF3. Nếu AZ-a mất, điều gì xảy ra?

**Gợi ý:** Cả ba replica có thể mất đồng thời. Nhãn rack không giúp gì nếu không phản ánh ba miền lỗi vật lý độc lập. Cần thay placement thực tế và lập lịch thay đổi topology đúng quy trình.

### Tình huống 2 — Hai rack nhưng RF3

Một DC có hai rack: rack-a chứa hai replica của partition, rack-b chứa một replica. CL đọc/ghi `LOCAL_QUORUM`. Nếu rack-a mất, cluster còn phục vụ được yêu cầu local quorum cho partition đó không?

**Gợi ý:** Không, chỉ còn một replica, trong khi local quorum RF3 cần hai. Phải thiết kế số miền lỗi và placement phù hợp với lỗi rack cần chịu.

### Tình huống 3 — Mất hoàn toàn một region

Hai DC có RF3 mỗi bên. Ứng dụng đã có khả năng chuyển sang region_b. Khi region_a mất, `LOCAL_QUORUM` tại region_b còn khả dụng nhưng `QUORUM` toàn cluster thì sao?

**Gợi ý:** Region_b còn ba replica, đủ local quorum là hai; nhưng global quorum của RF tổng 6 cần bốn, nên không đạt. Đây là đánh đổi giữa tính sẵn sàng vùng và mức nhất quán toàn cầu.

### Tình huống 4 — Hai local quorum trả hai giá trị

Trong lúc WAN đứt, hai ứng dụng mỗi ứng dụng ghi dữ liệu của cùng một partition ở DC riêng. Sau khi nối mạng lại, có thể dùng majority vote giữa các DC để chọn giá trị đúng không?

**Gợi ý:** Không. Cassandra dùng quy tắc hòa giải timestamp/tombstone và có nguy cơ tranh chấp nghiệp vụ. Cần thiết kế quy tắc ghi, chống xung đột (ví dụ LWT đúng phạm vi hoặc phân quyền ghi) và repair phù hợp; số DC không phải số phiếu biểu quyết.

### Tình huống 5 — Thêm region_b nhưng chưa có dữ liệu

Quản trị viên tạo node `region_b` và `ALTER KEYSPACE` thêm RF3. Ngay sau đó ứng dụng ở region_b gọi `LOCAL_QUORUM` và nhận dữ liệu thiếu hoặc lỗi. Có thể kết luận Cassandra mất toàn bộ dữ liệu không?

**Gợi ý:** Chưa. Thay metadata RF không có nghĩa toàn bộ bản sao đã được stream. Kiểm tra quy trình thêm DC/rebuild/repair, tình trạng topology và dữ liệu trên từng node trước khi bật traffic ứng dụng.

## 14. Checklist thiết kế trước khi đưa vào production

- [ ] Xác định **miền lỗi vật lý thực**: host, nguồn, switch, AZ, DC và đường WAN.
- [ ] Ánh xạ đúng **một DC Cassandra vào phạm vi latency/điều hành phù hợp** và rack vào những nhóm chịu lỗi độc lập.
- [ ] Không gán rack giả chỉ để tạo cảm giác replica phân tán.
- [ ] Kiểm tra `NetworkTopologyStrategy` và RF theo **đúng tên DC snitch báo**.
- [ ] Bố trí đủ rack cho mục tiêu RF và kịch bản mất một rack/AZ.
- [ ] Tính capacity/latency khi mất một node, một AZ hoặc cả DC, không chỉ trạng thái quorum lý thuyết.
- [ ] Lựa chọn `LOCAL_QUORUM`, `QUORUM` hoặc CL khác theo yêu cầu thật, hiểu ranh giới của local quorum giữa các DC.
- [ ] Triển khai routing/failover Java Driver, contact points và local DC có chủ đích.
- [ ] Kiểm tra internode network, streaming/repair, bảo mật/TLS và tuyến liên DC.
- [ ] Không đổi DC/rack trên node đang sống hoặc đổi RF trong production mà thiếu runbook streaming/repair.
- [ ] Có lịch repair liên DC khi yêu cầu, chính sách tombstone/TTL, backup và kế hoạch phục hồi.
- [ ] Thử nghiệm fault scenarios trên staging và giám sát p95/p99, error rates, disk/mạng sau thay đổi.

**Ghi nhớ:** `datacenter` và `rack` trong Cassandra là các **nhãn để placement và xác định phạm vi consistency**, không phải bằng chứng tự thân về độc lập hạ tầng. Một kiến trúc nhiều DC đáng tin cậy phải gắn các nhãn đó với **miền lỗi thật**, chọn RF và CL chịu được loại sự cố đã xác định, rồi bổ sung năng lực dự phòng, streaming/repair, giám sát và quy trình failover cho ứng dụng Java.
