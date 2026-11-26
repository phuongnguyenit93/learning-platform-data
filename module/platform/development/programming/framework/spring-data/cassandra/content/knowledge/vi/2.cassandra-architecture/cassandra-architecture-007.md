# Gossip, phát hiện node lỗi và thay đổi topology trong Apache Cassandra

## 1. Tại sao cần hiểu Gossip?

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình ngang hàng (**peer-to-peer**). Trong một cluster, node có thể khởi động, ngừng phản hồi, mất kết nối, phục hồi, gia nhập hoặc rời đi. Những node còn lại phải dần biết trạng thái của nhau để điều phối truy vấn và xác định replica có thể phục vụ yêu cầu.

**Gossip** là giao thức trao đổi thông tin về các node và trạng thái của cluster. Nó hỗ trợ phát hiện lỗi và nhận biết thay đổi topology mà không cần một node lãnh đạo cố định. Hiểu Gossip giúp người học **Spring Data Cassandra** giải thích vì sao cùng một câu CQL, repository hay **CassandraTemplate** có thể hoạt động bình thường, bị trễ hoặc gặp lỗi khi hạ tầng thay đổi. Kiến thức này bổ trợ cho thiết kế bảng theo truy vấn, partition key, consistency level, paging và kiểm soát hiệu năng trong hệ phân tán.

Bài học trả lời ba câu hỏi: **Gossip lan truyền gì? Cassandra nghi ngờ node lỗi thế nào? Khi thành viên cluster thay đổi thì dữ liệu và ứng dụng chịu ảnh hưởng ra sao?**

> Gossip truyền **metadata và trạng thái thành viên**, không phải toàn bộ hàng dữ liệu. Việc duy trì và chuyển các bản sao dữ liệu thuộc các cơ chế như replication, streaming, hinted handoff và repair.

## 2. Các khái niệm cần biết

| Thuật ngữ | Ý nghĩa trong kiến trúc Cassandra |
| --- | --- |
| **Cluster** | Tập hợp các node cùng phối hợp lưu trữ và phục vụ dữ liệu |
| **Node / endpoint** | Thành viên Cassandra và địa chỉ nhận diện khi các node trao đổi qua mạng |
| **Seed node** | Điểm liên lạc ban đầu để node mới tìm ra các thành viên khác; **không phải leader** |
| **Datacenter / rack** | Vị trí logic/vật lý của node, liên quan tới snitch và cách chọn replica |
| **Token / token range** | Cơ sở phân bố partition và trách nhiệm lưu trữ giữa các node |
| **Replica** | Node nắm một bản sao của dữ liệu thuộc partition theo replication strategy |
| **Coordinator** | Node tiếp nhận yêu cầu, điều phối replica cần đọc/ghi |
| **Topology** | Thành viên cluster, vị trí DC/rack, token và cách dữ liệu được phân phối |
| **Consistency level** | Mức xác nhận từ replica cần có để thao tác đọc/ghi hoàn tất theo quy tắc Cassandra |

Gossip và failure detector góp phần quyết định **góc nhìn hiện tại của một node** về các thành viên; replication strategy và consistency level quyết định yêu cầu cần bao nhiêu replica. Đây là các tầng liên quan nhưng không thay thế nhau.

## 3. Gossip hoạt động ra sao?

### 3.1. Lan truyền thông tin theo kiểu ngang hàng

Mỗi node duy trì một tập trạng thái cục bộ của các endpoint mà nó biết. Theo chu kỳ, node liên lạc với các peer để so sánh phiên bản trạng thái và trao đổi phần thay đổi cần thiết. Thông tin thu được từ một node lại có thể được chuyển cho các node khác trong các lượt sau, vì vậy cluster **hội tụ dần** về cùng một góc nhìn.

Quá trình Gossip thường gồm ba kiểu thông điệp khái niệm:

1. **Gossip SYN:** gửi bản tóm tắt những phiên bản trạng thái đang biết.
2. **Gossip ACK:** phản hồi thông tin mới mà bên gửi thiếu và yêu cầu thông tin còn thiếu từ bên kia.
3. **Gossip ACK2:** gửi nốt các trạng thái được yêu cầu.

Việc chọn peer, nhịp gửi và cấu trúc thông điệp cụ thể phụ thuộc triển khai/phiên bản. Điểm cốt lõi là mỗi lần trao đổi tập trung vào **cập nhật trạng thái**, không cần chép lại toàn bộ dữ liệu Cassandra.

~~~mermaid
sequenceDiagram
    participant A as Node A
    participant B as Node B
    participant C as Node C
    Note over A,C: Mỗi node có góc nhìn trạng thái riêng
    A->>B: Gossip SYN - tóm tắt phiên bản
    B-->>A: Gossip ACK - cập nhật và yêu cầu
    A->>B: Gossip ACK2 - thông tin bổ sung
    B->>C: Gossip trong lượt tiếp theo
    Note over A,C: Thông tin mới dần lan ra cluster
~~~

**Hệ quả:** tại một thời điểm, A có thể coi C là UP trong khi B đã nghi ngờ C bị lỗi. Gossip hướng tới sự hội tụ dần, không bảo đảm mọi node nhất trí tức thời về trạng thái khi mạng gặp sự cố.

### 3.2. Những trạng thái nào được trao đổi?

Các trường/khái niệm thường gặp khi quan sát trạng thái Gossip:

| Khái niệm | Ý nghĩa |
| --- | --- |
| **Generation** | Đại diện cho một vòng đời hoạt động của endpoint, giúp phân biệt trạng thái trước và sau khi khởi động lại |
| **Heartbeat version** | Phiên bản liên quan tới nhịp sống của node, tiến triển khi node hoạt động |
| **Application-state version** | Phiên bản của các trạng thái ứng dụng/metadata để xác định cập nhật nào mới hơn |
| **Status** | Trạng thái membership, như gia nhập, hoạt động bình thường hoặc rời cluster |
| **Host ID, token, datacenter, rack, metadata khác** | Giúp nhận diện thành viên và hiểu cấu trúc cluster theo phiên bản Cassandra |

Generation và version giúp một node so sánh dữ liệu nó đang giữ với dữ liệu peer thông báo. Ví dụ, A nhận thông tin mới về B; lượt sau A có thể giúp C biết cập nhật đó. Không có bước nào trong ví dụ này tự động chuyển SSTable từ B sang C.

### 3.3. Seed node không phải master

Node mới cần một số địa chỉ ban đầu để liên lạc và khám phá cluster: đó là **seeds** trong cấu hình Cassandra. Sau khi đã nhận biết các peer, node có thể trao đổi Gossip trực tiếp với các thành viên khác; các lượt đọc/ghi CQL cũng không buộc đi qua seed.

- **Seed** hỗ trợ khám phá thành viên, không nắm quyền điều phối toàn bộ cluster.
- Một seed bị lỗi không mặc nhiên làm các node đang chạy ngừng phục vụ yêu cầu.
- Cần cấu hình nhiều seed có thể tiếp cận và phù hợp topology theo hướng dẫn của phiên bản triển khai.
- **Seed của Cassandra** khác **contact points của Java driver**. Contact points là nơi ứng dụng kết nối ban đầu để driver khám phá cluster; driver không tham gia giao thức Gossip nội bộ.

## 4. Phát hiện node lỗi: phi-accrual failure detector

### 4.1. Không phản hồi chưa chắc đã chết

Giả sử B đột nhiên không nhận được cập nhật của A. A có thể đã dừng, nhưng cũng có thể mạng giữa hai máy gián đoạn, JVM của A bị dừng bởi garbage collection, CPU quá tải hoặc thông điệp bị trễ. Trong hệ phân tán, **không thể coi một lần im lặng là bằng chứng chắc chắn về nguyên nhân lỗi**.

Cassandra dùng bộ phát hiện lỗi kiểu **phi-accrual failure detector**. Cơ chế này theo dõi lịch sử khoảng thời gian giữa các quan sát nhịp sống của peer và tính mức độ nghi ngờ, ký hiệu **phi (φ)**. Khi khoảng thời gian chưa có cập nhật mới trở nên bất thường so với lịch sử, phi tăng. Nếu phi vượt ngưỡng cấu hình, node quan sát có thể đánh dấu peer là **DOWN**.

Đây là **phán đoán thống kê, có tính cục bộ**; một peer bị đánh dấu DOWN chưa chắc hỏng vĩnh viễn. Ngưỡng **phi_convict_threshold** ảnh hưởng độ nhạy và cần cân nhắc theo tải, mạng, JVM và phiên bản Cassandra. Thay đổi ngưỡng tùy tiện có thể gây phát hiện quá nhạy hoặc quá chậm.

~~~mermaid
flowchart TD
    A[Nhận heartbeat và Gossip] --> B[Theo dõi thời gian giữa các quan sát]
    B --> C[Tính mức nghi ngờ phi]
    C --> D{Vượt ngưỡng?}
    D -->|Không| E[Peer vẫn được coi là sẵn sàng]
    D -->|Có| F[Đánh dấu DOWN trong góc nhìn cục bộ]
    E --> A
    F --> G[Ảnh hưởng lựa chọn replica và xử lý request]
    G --> H[Tiếp tục nhận biết khả năng phục hồi]
~~~

### 4.2. Những tình huống dễ nhầm

| Quan sát | Có thể diễn giải | Không nên kết luận |
| --- | --- | --- |
| Tiến trình Cassandra trên A dừng | Peer có thể lần lượt đánh dấu A DOWN | Mọi dữ liệu lưu trên A đã mất |
| Network partition chia cluster thành các nhóm | Mỗi nhóm có thể nhìn nhận node phía kia khác nhau | Các node đã nhất trí tức thời về topology |
| A bị dừng GC lâu | Heartbeat bị trễ, có thể gây false positive | A chắc chắn phải được loại khỏi cluster |
| A trở lại và được thấy UP | Gossip nhận biết được trạng thái hiện tại | A đã bắt kịp toàn bộ dữ liệu bị bỏ lỡ |
| Client thấy ReadTimeout/WriteTimeout | Yêu cầu không hoàn tất đúng thời hạn | Node chắc chắn DOWN hoặc thao tác ghi chắc chắn chưa xảy ra |

**Gossip + failure detector** giúp các node nhận biết sức khỏe thành viên, nhưng chưa thay thế các phép kiểm tra thực tế: kết nối giữa replica, tài nguyên node, độ trễ CQL và trạng thái dữ liệu. Khi điều tra sự cố, kết hợp kết quả quan sát từ **nhiều node**, log và chỉ số mạng/GC trước khi thay đổi ngưỡng.

## 5. Gossip, topology và vòng đời của node

Topology thay đổi khi node gia nhập, được chủ động rút khỏi cluster, hỏng vĩnh viễn hoặc cần thay thế. Gossip hỗ trợ lan truyền **thông tin trạng thái** của những thay đổi này; Cassandra còn phải đảm bảo **đường phân bố dữ liệu** phù hợp với token và replication strategy.

| Trạng thái/tình huống | Ý nghĩa | Cơ chế/kiểm tra cần đi cùng |
| --- | --- | --- |
| **Joining / bootstrap** | Node mới tham gia, nhận trách nhiệm dữ liệu theo token range | Streaming dữ liệu, cập nhật replica placement và kiểm tra trạng thái gia nhập |
| **Normal** | Node hoạt động với nhiệm vụ lưu trữ theo topology hiện tại | Kiểm tra sức khỏe node, consistency và đường truy cập dữ liệu |
| **Leaving / decommission** | Node còn khỏe rời cluster có chủ đích | Chuyển trách nhiệm và dữ liệu sang các node còn lại |
| **Dead / removal** | Node mất hẳn và cần bị loại theo quy trình quản trị | Xác nhận lỗi vĩnh viễn, tái tạo replica và cập nhật membership |
| **Replacement** | Thay node chết bằng node khác theo quy trình hỗ trợ | Quản lý danh tính/token, streaming và trạng thái kết thúc |
| **Temporary outage / restart** | Node ngắt kết nối một lúc rồi phục hồi | Theo dõi Gossip, tình trạng dữ liệu bỏ lỡ và cơ chế repair phù hợp |

### 5.1. Node mới gia nhập

Giả sử cluster ban đầu có A, B, C và cần thêm D:

1. D liên lạc với các seeds để khám phá cluster.
2. Các node cập nhật nhận thức về thành viên mới, token và phân bố replica theo cấu hình.
3. D nhận các dải dữ liệu cần sở hữu thông qua **streaming**, thường từ các node đang giữ dữ liệu.
4. Sau khi hoàn tất điều kiện bootstrap, D chuyển sang **NORMAL**; quá trình khám phá topology của các node và client tiếp tục hội tụ.

~~~mermaid
flowchart LR
    A[Node A] <-->|Gossip| B[Node B]
    B <-->|Gossip| C[Node C]
    C <-->|Gossip| A
    D[Node D mới] -.->|Tìm thành viên| B
    A ==>|Streaming dữ liệu| D
    C ==>|Streaming dữ liệu| D
~~~

Sơ đồ mang tính khái niệm; node nguồn và token range cụ thể tùy topology, chiến lược replication và phân bổ token. **Gossip không thay thế quá trình streaming SSTable**. Khi quan sát, cần phân biệt node đang **JOINING** với node đã **NORMAL**.

### 5.2. Node rời cluster

Nếu node vẫn khỏe và muốn giảm số node, quy trình phù hợp thường là **decommission**, cho phép chuyển trách nhiệm dữ liệu trước khi rời đi. Nếu node đã hỏng và không thể hoạt động bình thường, phải dùng quy trình **remove dead node** thích hợp. Khi muốn thay node hỏng, cần theo hướng dẫn **replacement** tương ứng với phiên bản Cassandra.

Cần nhớ:

- Gossip đánh dấu node **DOWN** không đồng nghĩa node đã bị xóa khỏi cluster. Một sự cố tạm thời có thể phục hồi.
- Thay đổi số node không tự thay đổi **replication factor** của keyspace.
- Mạng và tài nguyên có thể chịu thêm tải vì streaming, tái phân bố dữ liệu và repair.
- Không tự ý tái sử dụng danh tính/token của node hỏng bằng thao tác khởi động thông thường.
- Node vừa **UP/NORMAL** không bảo đảm mọi replica đã có cùng dữ liệu; cần kiểm tra thêm dữ liệu và quy trình repair khi phù hợp.

## 6. Tình huống: một node bị lỗi ảnh hưởng truy vấn CQL thế nào?

Xét **một datacenter** gồm A, B, C. Một keyspace đặt **replication factor = 3**, nên trong ví dụ dữ liệu partition được sao chép trên cả ba node. Có thể hình dung cấu hình keyspace:

~~~sql
CREATE KEYSPACE app_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

**dc1 chỉ là tên minh họa**, phải khớp datacenter thực tế. Ví dụ giả định cluster và keyspace đã được cấu hình đúng; không dùng nguyên mẫu này để thay đổi keyspace đang có dữ liệu sản xuất.

### 6.1. Khi A, B, C đều hoạt động

Ứng dụng Spring Data Cassandra gửi truy vấn qua Java driver tới một **coordinator**; coordinator xử lý yêu cầu theo partition key, vị trí replica và consistency level. Với RF = 3 ở một datacenter, **LOCAL_QUORUM** yêu cầu phản hồi phù hợp từ **ít nhất hai replica**. Một truy vấn vẫn có thể chậm vì hot partition hoặc CQL không phù hợp dù cả ba node đều UP.

### 6.2. Khi B ngừng phản hồi

1. A và C không còn nhận cập nhật như bình thường từ B; mỗi node tích lũy mức nghi ngờ riêng.
2. Sau một khoảng thời gian, A/C có thể đánh dấu B là DOWN. Thời điểm của hai node không nhất thiết trùng nhau.
3. Nếu A và C vẫn phục vụ được cùng dữ liệu, yêu cầu **LOCAL_QUORUM** có thể thành công nhờ **hai replica** còn lại.
4. Nếu chỉ còn một replica có thể phản hồi, không thể đáp ứng **LOCAL_QUORUM** cho partition đó. Nếu dùng consistency level khác, đánh đổi giữa độ sẵn sàng và bảo đảm đọc/ghi cũng khác.
5. Khi B trở lại, các cơ chế khôi phục và đồng bộ dữ liệu có thể phải xử lý những cập nhật B bỏ lỡ; **chỉ riêng Gossip không khẳng định dữ liệu đã đồng bộ**.

Lỗi **Unavailable**, **ReadTimeout**, **WriteTimeout** và lỗi kết nối là những biểu hiện của **yêu cầu cụ thể**, có thể liên quan topology nhưng không giống với sự kiện “node B DOWN”. Đặc biệt, WriteTimeout không chứng minh chắc chắn rằng không replica nào đã ghi dữ liệu.

### 6.3. Mối liên hệ với Spring Data Cassandra

**Entity mapping** ánh xạ bảng/khóa Cassandra sang Java. **Repository** cung cấp cách tổ chức truy vấn; **CassandraTemplate** giúp chủ động thao tác với CQL. Cả hai đều qua driver tới cluster, đều chịu ảnh hưởng của topology và consistency level. **Thiết kế partition key** vẫn quan trọng: đổi repository sang template không sửa được partition quá lớn, truy vấn không theo khóa hay hot partition.

## 7. Quan sát Gossip và thay đổi topology

Trong môi trường thử nghiệm được phép thao tác, công cụ **nodetool** cung cấp góc nhìn của một node:

~~~bash
# Trạng thái thành viên, DC/rack và thông tin node
nodetool status

# Thông tin Gossip mà node hiện quan sát
nodetool gossipinfo

# Thông tin tổng quan về cluster
nodetool describecluster

# Tiến độ streaming và hoạt động mạng liên quan
nodetool netstats
~~~

Đầu ra **nodetool status** thường ghép hai loại trạng thái: **U/D** (Up/Down) và **N/J/L/...** (Normal/Joining/Leaving/...). **UN** nghĩa là node **Up/Normal** theo nơi chạy lệnh; **DN** nghĩa là node được nhìn nhận **Down/Normal**, không có nghĩa node đó đã bị xóa vĩnh viễn. Tên trạng thái và chi tiết hiển thị có thể khác theo phiên bản.

Khi đọc số liệu:

1. So sánh quan sát từ nhiều node nếu nghi Gossip chưa hội tụ.
2. Kiểm tra log, GC, mạng, CPU và độ trễ CQL để tìm nguyên nhân một node bị đánh dấu DOWN.
3. Theo dõi streaming khi node đang bootstrap, decommission hoặc được thay thế.
4. Kiểm tra thông tin **datacenter/rack**, replication factor và khả năng đáp ứng consistency level của ứng dụng.
5. Phân biệt trạng thái **UP** với việc dữ liệu đã được kiểm tra tính nhất quán; dùng các cơ chế vận hành phù hợp để xác minh phần dữ liệu còn thiếu.

## 8. Spring Data Cassandra kết nối và xử lý lỗi như thế nào?

Ứng dụng Spring Boot dùng các **contact points**, local datacenter và keyspace để Java driver tìm cluster. Ví dụ với những thế hệ Spring Boot sử dụng nhóm thuộc tính **spring.cassandra**:

~~~yaml
spring:
  cassandra:
    contact-points: 127.0.0.1
    port: 9042
    local-datacenter: dc1
    keyspace-name: app_ks
~~~

Tên thuộc tính và yêu cầu cấu hình phụ thuộc phiên bản Spring Boot/Spring Data/driver. Địa chỉ **127.0.0.1** chỉ đúng nếu ứng dụng thật sự truy cập Cassandra từ đó. Trong triển khai nhiều node, khai báo contact points có thể tiếp cận và chọn local datacenter chính xác. Java driver **không trao đổi Gossip** như một node Cassandra; nó khám phá metadata và theo dõi các endpoint qua cơ chế của driver.

| Tầng | Trách nhiệm |
| --- | --- |
| **Gossip** | Lan truyền thông tin endpoint, membership và topology |
| **Failure detector** | Đánh giá khả năng peer còn phản hồi theo quan sát thống kê |
| **Replication/streaming/repair** | Lưu, chuyển hoặc đồng bộ các bản sao dữ liệu theo cơ chế tương ứng |
| **Java driver** | Kết nối, chọn node điều phối, quản lý metadata và xử lý yêu cầu/lỗi theo chính sách |
| **Spring Data Cassandra** | Mapping entity, repository, CassandraTemplate và truy cập CQL |

Ứng dụng cần có chính sách timeout và retry có giới hạn, sử dụng consistency level theo nghiệp vụ, quan sát latency, đồng thời đảm bảo **idempotency** hoặc cơ chế chống ghi trùng khi một thao tác có thể bị thử lại. Không retry vô hạn chỉ vì một node vừa chuyển trạng thái, và không suy luận từ một lần WriteTimeout rằng lần ghi chắc chắn thất bại.

## 9. Bài thực hành trên cluster thử nghiệm

Chỉ dừng hoặc thay đổi node trên **cluster thử nghiệm do bạn quản lý**, không tác động môi trường đang phục vụ người dùng.

### Phần A — Nhận biết cluster

1. Chuẩn bị cluster Cassandra thử nghiệm có ba node trong một datacenter và một ứng dụng Spring Data Cassandra kết nối được.
2. Chạy **nodetool status** và **nodetool gossipinfo**, ghi lại host ID, DC/rack và trạng thái các node.
3. Chạy một truy vấn CQL với partition key đầy đủ, ghi độ trễ và consistency level.
4. Giải thích sự khác nhau giữa **Cassandra seeds** và **Java driver contact points**.

### Phần B — Lỗi tạm thời và hồi phục

1. Trong môi trường thử nghiệm, dừng một node bằng thao tác quản trị thích hợp.
2. Quan sát từ ít nhất hai node còn hoạt động, ghi lúc mỗi nơi đánh dấu peer **DOWN**.
3. Thử truy vấn ở **LOCAL_QUORUM** với RF = 3, giải thích tại sao hai replica khỏe có thể đủ và một replica thì không đủ.
4. Khởi động lại node đã dừng, quan sát thay đổi **UP**, log và kết quả đọc/ghi.
5. Ghi rõ vì sao sự phục hồi trong Gossip và việc bắt kịp dữ liệu của replica là hai khâu khác nhau.

### Phần C — Thay đổi topology trên giấy hoặc môi trường nhỏ

Mô tả đường đi của node D khi gia nhập: khám phá seed, trao đổi Gossip, nhận token range, **streaming** và chuyển từ **JOINING** sang **NORMAL**. Sau đó so sánh ba tình huống: node khỏe **decommission**, node hỏng hẳn cần **remove**, và **replace** một node lỗi. Nêu biện pháp kiểm tra sau mỗi tình huống; không phải thao tác thật nếu môi trường không đủ tài nguyên.

**Tiêu chí hoàn thành:** người học phân biệt chính xác *thông tin trạng thái*, *phán đoán lỗi*, *thay đổi membership* và *di chuyển/đồng bộ dữ liệu*; giải thích được ảnh hưởng lên yêu cầu CQL ở consistency level đã chọn.

## 10. Các hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Seed là master, seed chết cluster dừng.” | Seed giúp khám phá ban đầu; các node Cassandra phối hợp ngang hàng |
| “Không nhận heartbeat tức là node đã chết.” | Có thể do mạng, GC hoặc quá tải; failure detector đánh giá mức nghi ngờ |
| “Mọi node biết trạng thái DOWN ngay lập tức.” | Mỗi node quan sát riêng và Gossip hội tụ dần |
| “Gossip sao chép tất cả dữ liệu cho node mới.” | Dữ liệu được chuyển qua streaming, Gossip lan truyền trạng thái |
| “Node vừa UP nghĩa là dữ liệu đã nhất quán hoàn toàn.” | Trạng thái sống không chứng nhận mọi replica đã bắt kịp |
| “Bị DOWN thì xóa node ngay.” | Lỗi tạm thời và loại node vĩnh viễn là hai quy trình khác nhau |
| “Repository xử lý hết sự cố phân tán.” | Vẫn phải thiết kế CQL, timeout, retry, idempotency và consistency |

## 11. Tự kiểm tra

1. Vì sao Gossip phù hợp mô hình peer-to-peer? Nó có sao chép toàn bộ dữ liệu không?
2. Generation và version có ích gì khi node ngừng hoạt động rồi trở lại?
3. Seed nodes và contact points khác nhau ở đâu?
4. Vì sao phi-accrual failure detector có thể đánh dấu nhầm node khỏe thành DOWN?
5. Hai node có thể bất đồng tạm thời về trạng thái node thứ ba không?
6. Với RF = 3 cùng một datacenter, một replica DOWN có luôn khiến LOCAL_QUORUM thất bại không?
7. Vì sao quá trình thêm node cần streaming ngoài Gossip?
8. Decommission một node còn khỏe khác gì loại một node đã hỏng vĩnh viễn?
9. Tại sao một node vừa UP không chứng minh dữ liệu đã được đồng bộ đủ?
10. Nếu ghi qua Spring Data Cassandra bị WriteTimeout, cần cân nhắc gì trước khi retry?

Khi đã kết nối được chuỗi **Gossip → phát hiện lỗi → góc nhìn topology → chọn replica/consistency → kết quả truy vấn CQL**, người học có nền tảng để đi sâu vào replication, repair, paging và tối ưu hiệu năng trên Cassandra.
