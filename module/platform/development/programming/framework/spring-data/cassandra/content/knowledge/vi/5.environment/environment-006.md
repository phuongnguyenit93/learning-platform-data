# Địa chỉ kết nối, cổng và local datacenter trong Spring Data Cassandra

## 1. Mục tiêu của bài học

Để dùng **Spring Data Cassandra** truy cập Apache Cassandra bằng entity mapping, repository, `CassandraTemplate` hoặc truy vấn CQL, ứng dụng phải kết nối được tới cluster trước tiên. Ba thông tin thường gây nhầm lẫn nhất là **địa chỉ kết nối (contact points)**, **cổng native transport** và **local datacenter**. Chúng liên quan với nhau nhưng đảm nhiệm các vai trò khác nhau:

- **Contact points:** những địa chỉ node Cassandra mà Java driver có thể liên hệ khi khởi tạo và khám phá cluster.
- **Port:** cổng mạng mà dịch vụ **CQL native protocol** lắng nghe, thường là **9042** theo cấu hình mặc định.
- **Local datacenter:** tên datacenter của Cassandra mà driver sử dụng làm khu vực ưu tiên để gửi yêu cầu theo chính sách định tuyến phù hợp.

Bài này hướng dẫn xác định ba giá trị từ môi trường thực tế, khai báo trong ứng dụng Spring Boot, phân biệt địa chỉ giữa máy host, container và máy chủ từ xa, đồng thời xử lý các lỗi kết nối phổ biến. Sau bài học, bạn nên tự giải thích được vì sao ứng dụng có thể ping một node nhưng vẫn không truy cập Cassandra thành công, hoặc vì sao đổi địa chỉ kết nối không giải quyết được lỗi khai báo local datacenter.

## 2. Một yêu cầu CQL đi từ ứng dụng tới Cassandra như thế nào?

Ứng dụng Spring Data Cassandra sử dụng **Java driver** để tạo phiên làm việc tới cluster. Khi khởi tạo, driver liên hệ một hoặc vài contact points, tìm hiểu metadata và những node khác, sau đó chọn node phù hợp làm **coordinator** cho từng yêu cầu.

~~~mermaid
flowchart LR
    A[Spring Boot: repository / CassandraTemplate] --> B[Java driver: CqlSession]
    B -->|Kết nối khởi tạo| C[Contact point: Node A, TCP 9042]
    C -.->|Metadata cluster| B
    B -->|Truy vấn về sau| D[Node B: coordinator]
    B -->|Truy vấn về sau| E[Node C: coordinator]
    D --> F[Replica dữ liệu theo partition key]
    E --> F
~~~

Sơ đồ mang tính khái niệm: contact point ban đầu cũng có thể trở thành coordinator, và node thực tế được chọn phụ thuộc driver, topology, trạng thái kết nối cùng cấu hình. Driver có thể gửi các truy vấn kế tiếp đến node **không nằm trong danh sách contact points**, miễn là node đó đã được khám phá và ứng dụng có thể kết nối tới địa chỉ node được quảng bá.

**Điểm mấu chốt:** contact points dùng để **đi vào cluster và tìm hiểu topology**, không phải danh sách cố định của những node duy nhất được phép nhận truy vấn, và cũng không phải cấu hình xác định partition key hay replica.

## 3. Contact points: nên khai báo địa chỉ nào?

### 3.1. Một contact point là gì?

Contact point là **hostname hoặc địa chỉ IP** của node Cassandra mà tiến trình ứng dụng thực sự có thể kết nối qua giao thức CQL. Ví dụ:

| Nơi chạy Spring Boot | Địa chỉ có thể phù hợp | Điều kiện |
| --- | --- | --- |
| Ứng dụng chạy trực tiếp trên máy có Cassandra local | `127.0.0.1` | Cassandra mở native transport trên interface/port phù hợp với kết nối loopback |
| Spring Boot chạy trên host, Cassandra chạy trong container | `127.0.0.1` với port đã publish ra host | Container phải publish cổng 9042 (hoặc cổng host tương ứng) |
| Spring Boot và Cassandra chạy trong cùng mạng Docker Compose | Tên service, ví dụ `cassandra` | Hai container phải phân giải tên nhau và có kết nối mạng tới cổng container |
| Spring Boot chạy ở máy khác trong mạng nội bộ | DNS/IP có thể định tuyến, ví dụ `cassandra-a.internal` | Firewall, DNS, địa chỉ node được quảng bá và chính sách truy cập phải đúng |
| Ứng dụng chạy trong Kubernetes | Địa chỉ service/headless service hoặc endpoint theo cấu hình driver/operator | Các node Cassandra mà driver khám phá phải tiếp tục kết nối được từ Pod ứng dụng |

**`localhost` luôn chỉ máy hoặc network namespace của chính tiến trình ứng dụng.** Nếu Spring Boot chạy trong container riêng, `127.0.0.1` chỉ container Spring Boot, không phải container Cassandra. Đây là một trong những nguyên nhân phổ biến của lỗi “chạy CQL trên host được nhưng ứng dụng không kết nối”.

### 3.2. Tại sao nên có nhiều contact points?

Trong cluster nhiều node, danh sách nhiều contact points giúp driver vẫn có cơ hội khám phá cluster khi một node ban đầu bị lỗi:

~~~yaml
spring:
  cassandra:
    contact-points:
      - cassandra-a.internal
      - cassandra-b.internal
      - cassandra-c.internal
    port: 9042
    local-datacenter: dc1
    keyspace-name: app_ks
~~~

Ví dụ sử dụng nhóm thuộc tính **`spring.cassandra`** trong các thế hệ Spring Boot hiện đại. Tên miền, datacenter và keyspace đều là ví dụ minh họa, không phải giá trị mặc định phải dùng.

Ba contact points **không** có nghĩa mỗi truy vấn sẽ được gửi đến cả ba node. Java driver lựa chọn coordinator theo chính sách định tuyến và metadata. Cũng không cần liệt kê mọi node trong một cluster lớn: cần đủ endpoint tin cậy, có thể tiếp cận, phù hợp với cách driver khám phá topology.

### 3.3. Contact points khác seed nodes và coordinator

| Khái niệm | Ai sử dụng? | Vai trò |
| --- | --- | --- |
| **Contact points** | Java driver ở phía ứng dụng | Liên lạc ban đầu để khám phá cluster |
| **Seeds** | Các tiến trình Cassandra | Giúp các node tìm nhau thông qua Gossip khi tham gia cluster |
| **Coordinator** | Cassandra xử lý từng request | Nhận và điều phối một yêu cầu đọc/ghi tới các replica |
| **Replica** | Cassandra lưu dữ liệu | Chứa bản sao partition theo replication strategy |

Contact point **không phải seed bắt buộc**, cũng không nhất thiết là coordinator cho mọi truy vấn. Thay contact points của ứng dụng không tự thay topology hay replication factor của Cassandra.

## 4. Cổng kết nối: native transport và những cổng khác

Cassandra hỗ trợ giao thức **CQL native transport** để client gửi các truy vấn. Cổng thông dụng là **9042/TCP**, nhưng giá trị thực tế có thể được thay đổi trong cấu hình server hoặc được ánh xạ sang cổng khác qua container, proxy hay dịch vụ hạ tầng.

| Cổng thường gặp | Mục đích | Spring Data Cassandra có dùng làm cổng CQL không? |
| --- | --- | --- |
| **9042/TCP** | Native transport/CQL client | **Có**, nếu server đang lắng nghe tại đây |
| **7000/TCP** | Giao tiếp giữa các node Cassandra trong những cấu hình phổ biến | **Không** |
| **7001/TCP** | Giao tiếp internode có mã hóa ở một số cấu hình/phiên bản | **Không** |
| **7199/TCP** | JMX, thường dùng cho công cụ quản trị như `nodetool` | **Không** |

Không nên tự chuyển `spring.cassandra.port` sang 7000 hoặc 7199 khi gặp lỗi kết nối; các cổng đó phục vụ những giao thức khác. Khi dùng TLS cho kết nối CQL, cổng thực tế **phụ thuộc cấu hình máy chủ hoặc dịch vụ được quản lý**; không có một cổng TLS chung bắt buộc cho mọi môi trường.

### 4.1. Phân biệt cổng bên ngoài và bên trong container

Giả sử chạy Cassandra với ánh xạ cổng:

~~~bash
docker run --name cassandra-lab -p 19042:9042 -d cassandra
~~~

Khi container đã khởi động và Cassandra sẵn sàng:

- Ứng dụng chạy **trên máy host** có thể kết nối tới `127.0.0.1:19042`.
- Ứng dụng chạy **cùng mạng Docker với Cassandra** thường dùng địa chỉ container/service và **cổng container 9042**; không dùng `19042` nếu đang kết nối nội bộ trực tiếp.
- Ánh xạ `19042:9042` chỉ chuyển tiếp kết nối ở ranh giới host/container, không thay đổi cổng native transport lắng nghe bên trong Cassandra.

Lệnh minh họa không cấu hình tên datacenter hay keyspace. Cần kiểm tra các giá trị đó trước khi đặt chúng vào ứng dụng.

### 4.2. Kiểm tra tầng mạng trước khi điều tra CQL

Trên máy có thể truy cập endpoint:

~~~bash
# Nếu có cqlsh và máy chủ cho phép kết nối không yêu cầu TLS đặc biệt:
cqlsh cassandra-a.internal 9042

# Linux/macOS: chỉ kiểm tra TCP socket có thể tiếp cận
nc -vz cassandra-a.internal 9042
~~~

Trên Windows PowerShell:

~~~powershell
Test-NetConnection cassandra-a.internal -Port 9042
~~~

**TCP mở không đồng nghĩa truy vấn CQL đã chạy thành công.** Các bước sau vẫn có thể thất bại do TLS, xác thực, tương thích giao thức hoặc chọn sai local datacenter. Ngược lại, `cqlsh` từ máy host thành công không chứng minh container chạy ứng dụng có cùng khả năng định tuyến tới mọi node.

## 5. Local datacenter: tên gì và lấy ở đâu?

### 5.1. Datacenter là khái niệm logic của Cassandra

Một Cassandra cluster có thể gồm một hoặc nhiều **datacenter** (DC). Tên DC được xác định theo cấu hình topology/snitch của các node; đây là thông tin cluster, **không phải chuỗi do ứng dụng tự đặt**. Ví dụ một cluster có hai DC tên `dc1` và `dc2`; cluster khác có thể đặt `datacenter1` hoặc `hcm-prod`. Tên thực tế phải được xác minh.

**Local datacenter** của Java driver là DC mà ứng dụng ưu tiên sử dụng theo chính sách định tuyến có nhận thức DC. Nó thường được chọn cùng vùng mạng/khu vực triển khai với ứng dụng nhằm giảm truy cập liên vùng và phù hợp kế hoạch replica/consistency. Chữ “local” **không tự có nghĩa là localhost**, và việc đổi nó **không di chuyển dữ liệu hay đổi DC của Cassandra**.

### 5.2. Cách tìm local datacenter thực tế

Nếu có quyền trên một node Cassandra:

~~~bash
nodetool status
~~~

Đầu ra có thể chứa đoạn tương tự:

~~~text
Datacenter: dc1
================
Status=Up/Down
|/ State=Normal/Leaving/Joining/Moving
--  Address      Load       Tokens  Owns   Host ID  Rack
UN  10.0.0.11    ...        ...     ...    ...      rack1
UN  10.0.0.12    ...        ...     ...    ...      rack2
~~~

Hoặc từ phiên `cqlsh` đang kết nối đến một node:

~~~sql
SELECT data_center, rack FROM system.local;
~~~

Truy vấn `system.local` trả về DC/rack của **node đang phục vụ phần thông tin cục bộ đó**, không tự cho biết datacenter thích hợp nhất cho mọi ứng dụng nếu cluster có nhiều DC. Phải đối chiếu với topology thực tế và vùng triển khai của ứng dụng.

**Ví dụ:** nếu `nodetool status` cho thấy nhóm node ứng dụng cần dùng thuộc `Datacenter: dc1` thì cấu hình driver chọn `local-datacenter: dc1`. Đừng đoán bằng tên keyspace, địa chỉ IP, host name hay tên region của cloud; các giá trị có thể không giống tên DC thực tế.

### 5.3. Local DC, replication và consistency level

Giả sử một cluster có hai datacenter:

| DC | Số node | Replication factor của `app_ks` | Ứng dụng |
| --- | ---: | ---: | --- |
| `dc1` | 3 | 3 | API chạy gần các node ở `dc1` |
| `dc2` | 3 | 3 | API dự phòng chạy gần các node ở `dc2` |

Với keyspace dùng `NetworkTopologyStrategy`:

~~~sql
CREATE KEYSPACE app_ks
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3,
    'dc2': 3
};
~~~

Nếu ứng dụng chủ yếu hoạt động tại `dc1`, local datacenter thường được chọn là `dc1`. Khi chọn consistency level `LOCAL_QUORUM`, Cassandra đánh giá quorum **trong DC local của coordinator/operation theo quy tắc consistency**, thay vì yêu cầu quorum trên tổng số replica của cả hai datacenter. Với RF = 3 tại DC đó, local quorum cần **2 replica** phản hồi phù hợp.

**Hai cấu hình có trách nhiệm riêng:** `spring.cassandra.local-datacenter` hướng dẫn **client** chọn node theo DC, còn replication factor trong keyspace hướng dẫn **Cassandra** lưu các bản sao dữ liệu ở đâu. Việc chọn local DC không tự tăng/giảm RF và không tự bảo đảm độ nhất quán mạnh của mọi truy vấn.

Nếu nhập sai DC, tùy driver và topology, ứng dụng có thể không khởi tạo được phiên, không chọn được node phù hợp hoặc gặp lỗi liên quan metadata/định tuyến. Khi đó cần xác minh tên DC thực tế và khả năng truy cập các node, thay vì tăng timeout ngay lập tức.

## 6. Cấu hình trong Spring Boot và Java driver

### 6.1. Spring Boot: một node local để học

Ví dụ với Cassandra local có DC tên **`datacenter1`** và keyspace `lab_ks` đã được tạo:

~~~yaml
spring:
  cassandra:
    contact-points:
      - 127.0.0.1
    port: 9042
    local-datacenter: datacenter1
    keyspace-name: lab_ks
~~~

Các giá trị ở đây **chỉ là ví dụ**. Một môi trường Cassandra khác có thể dùng `dc1`; cần kiểm tra bằng `nodetool`/`system.local`. Keyspace là không gian lưu trữ các bảng CQL, khác với tên DC và không quyết định địa chỉ mạng.

Ứng dụng Spring Boot thường thêm dependency `spring-boot-starter-data-cassandra` và để auto-configuration tạo kết nối phù hợp với properties. Repository và `CassandraTemplate` sử dụng hạ tầng kết nối đã cấu hình; không cần tự tạo mỗi API một kết nối riêng.

### 6.2. Các thế hệ Spring Boot có tên property khác nhau

| Môi trường | Nhóm property phổ biến | Lưu ý |
| --- | --- | --- |
| **Spring Boot 3.x** | `spring.cassandra.*` | Các ví dụ trong bài dùng nhóm này |
| **Spring Boot 2.x, gồm nhiều ứng dụng 2.7** | `spring.data.cassandra.*` | Chuyển prefix theo phiên bản đang chạy; tránh trộn hai nhóm |
| **Java driver sử dụng trực tiếp** | `CqlSession.builder()` hoặc cấu hình driver riêng | Cần khai báo contact points và local DC theo API/version của driver |
| **Cassandra dịch vụ được quản lý** | Phụ thuộc provider: bundle, endpoint, TLS/authentication | Hướng dẫn của provider có thể thay cách khai báo contact points |

Ví dụ dùng **Java driver 4.x** trực tiếp ở một ứng dụng không dựa vào auto-configuration:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

public class ConnectionExample {
    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress("cassandra-a.internal", 9042))
                .addContactPoint(new InetSocketAddress("cassandra-b.internal", 9042))
                .withLocalDatacenter("dc1")
                .build()) {
            System.out.println(session.getMetadata().getNodes().size());
        }
    }
}
~~~

Đây là **ví dụ Java driver độc lập**, không phải cấu hình đồng thời với Spring Boot ở trên. Trong Spring Boot, ưu tiên để auto-configuration quản lý `CqlSession` và vòng đời tài nguyên trừ khi có yêu cầu rõ ràng phải tự tạo bean. API và thư viện driver cụ thể có thể khác theo tổ hợp phiên bản.

### 6.3. Biến môi trường và triển khai

Trong cấu hình Spring Boot hỗ trợ relaxed binding, có thể cấp giá trị qua môi trường triển khai, chẳng hạn:

~~~text
SPRING_CASSANDRA_CONTACT_POINTS=cassandra-a.internal,cassandra-b.internal
SPRING_CASSANDRA_PORT=9042
SPRING_CASSANDRA_LOCAL_DATACENTER=dc1
SPRING_CASSANDRA_KEYSPACE_NAME=app_ks
~~~

Các biến trên chỉ chứa **thông tin endpoint** và keyspace. Khi cluster bật xác thực hoặc TLS, cấu hình bổ sung thông tin đăng nhập, chứng chỉ CA/truststore và lựa chọn mã hóa theo driver/phiên bản; không ghi mật khẩu hoặc khóa bí mật trực tiếp vào Git. Đừng tắt kiểm tra chứng chỉ chỉ để bỏ qua lỗi hostname hay CA chưa tin cậy.

## 7. Khi kết nối qua Docker, Kubernetes và môi trường từ xa

### 7.1. Docker Compose: dùng tên service bên trong network

Giả sử service ứng dụng và Cassandra đều nằm trong cùng Docker Compose network. Một cấu hình có thể dùng:

~~~yaml
spring:
  cassandra:
    contact-points:
      - cassandra
    port: 9042
    local-datacenter: dc1
    keyspace-name: lab_ks
~~~

Trong ví dụ, `cassandra` là tên service có thể phân giải DNS trong network. Tên DC `dc1` phải đúng với Cassandra thực tế: việc đặt tên service `cassandra` **không tự đặt tên DC**. Đồng thời, cần có chiến lược readiness: container khởi động chưa có nghĩa native transport đã sẵn sàng nhận phiên CQL.

### 7.2. Kubernetes: service đầu vào chưa đủ

Với Cassandra chạy trong Kubernetes, client có thể kết nối qua DNS của service hoặc headless service phù hợp với operator/driver. Nhưng driver thường **khám phá các endpoint node từ metadata cluster**, nên các địa chỉ được quảng bá sau discovery cũng phải có thể kết nối từ Pod ứng dụng.

Nếu driver khởi tạo được phiên tại một endpoint nhưng mất kết nối khi gửi truy vấn tới các node khác, hãy kiểm tra:

1. Tên DNS có được phân giải từ Pod ứng dụng không?
2. Service/port có chuyển tiếp đúng giao thức CQL không?
3. Các địa chỉ node Cassandra quảng bá ra có định tuyến được từ Pod đó không?
4. NetworkPolicy, firewall, TLS và xác thực có cho phép kết nối tới các endpoint đã khám phá không?
5. Local datacenter đã chọn có khớp DC của các node mà driver có thể truy cập không?

Không tự giả định rằng một load balancer TCP duy nhất giải quyết hoàn toàn discovery hoặc định tuyến trong cluster nhiều node; các yêu cầu cụ thể tùy driver và mô hình triển khai.

### 7.3. Máy chủ từ xa: địa chỉ lắng nghe và quảng bá

Máy chủ Cassandra có thể **lắng nghe** trên một địa chỉ/interface và **quảng bá** địa chỉ khác để client liên lạc. Tùy phiên bản Cassandra, các cài đặt native transport/broadcast cho client có thể liên quan đến `rpc_address`, `broadcast_rpc_address` và `native_transport_port`. Phân biệt với địa chỉ/port trao đổi **giữa các node**.

Ví dụ một node nghe CQL trên interface nội bộ, nhưng driver ở mạng khác chỉ biết địa chỉ riêng không thể truy cập. Lúc này việc mở cổng trên một contact point có thể chưa đủ: các địa chỉ peer mà driver khám phá cũng cần hợp lệ. Điều chỉnh cấu hình server cần phù hợp topology, networking, bảo mật và hướng dẫn vận hành của phiên bản; không thay tùy tiện trên cluster đang hoạt động.

## 8. Chẩn đoán theo từng lớp khi ứng dụng không kết nối được

**Quy trình ưu tiên:** phân giải DNS → mở TCP tới cổng native → thương lượng CQL/TLS → xác thực → khám phá topology → chọn local DC → truy cập keyspace/bảng → thực hiện truy vấn nghiệp vụ.

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra ưu tiên |
| --- | --- | --- |
| `Connection refused` | Không có tiến trình nghe trên địa chỉ/cổng đó, hoặc port publish sai | Kiểm tra native transport và port ánh xạ từ chính nơi chạy ứng dụng |
| Kết nối hết thời gian chờ | Firewall, routing, DNS/IP không thể tới | Dùng `nc`/`Test-NetConnection` từ đúng môi trường của ứng dụng |
| Kết nối contact point được nhưng các node khác thất bại | Node quảng bá endpoint không thể tiếp cận | Kiểm tra metadata driver, địa chỉ broadcast và network policy |
| Driver báo local DC không hợp lệ/không tìm thấy node phù hợp | Tên DC sai hoặc cấu hình DC không tương thích topology | Xem `nodetool status`, `system.local` và cấu hình driver |
| TLS handshake/SSL lỗi | Server/client không thống nhất TLS, chứng chỉ không được tin cậy, tên máy không khớp | Kiểm tra SSL config, truststore và chứng chỉ theo chuẩn môi trường |
| Lỗi xác thực | Username/password hoặc cơ chế authentication sai | Kiểm tra user/quyền, secret injection và cấu hình driver |
| Kết nối thành công nhưng CQL lỗi `unconfigured keyspace` | Keyspace chưa tạo hoặc tên khai báo sai | Kiểm tra tên keyspace và quyền truy cập |
| Query chậm hoặc timeout dù kết nối thành công | Hot partition, replica chậm, consistency, tải cluster, mạng | Đo latency, xem truy vấn CQL/partition key và trạng thái replica |

### 8.1. Quy trình thực tế từng bước

1. **Đọc cấu hình đang được áp dụng** của Spring Boot: contact points, port, local datacenter, keyspace, TLS/auth. Tránh chỉ nhìn file `application.yml` nếu deployment có environment variables hoặc cấu hình ưu tiên khác.
2. **Xác minh địa chỉ từ nơi chạy ứng dụng.** Trên máy host và trong container có thể cho kết quả DNS/loopback khác nhau.
3. **Kiểm tra cổng TCP.** Nếu không mở được socket, tập trung vào routing, service, firewall, port publish và trạng thái server.
4. **Thử giao thức CQL** bằng `cqlsh` hoặc công cụ client tương thích từ cùng vùng mạng, với chính sách TLS/auth tương ứng.
5. **Kiểm tra DC từ Cassandra** thay vì đoán: `nodetool status` hoặc `SELECT data_center FROM system.local;`.
6. **Xác minh driver khám phá được các node.** Các endpoint được quảng bá phải truy cập được; khi cần xem log metadata/topology của driver ở mức phù hợp, tránh log thông tin nhạy cảm.
7. **Kiểm tra keyspace và quyền**, sau đó mới chạy câu CQL theo partition key của ứng dụng.
8. **Đo kết quả thực tế** khi mất node hoặc đang streaming, vì kết nối khởi tạo thành công không đảm bảo mỗi truy vấn luôn thành công.

Không nên dùng `ALLOW FILTERING`, tăng timeout vô hạn hoặc chỉnh consistency level một cách tùy tiện để che lỗi network/topology. Nếu một request trả `WriteTimeout`, thao tác ghi có thể đã đến một phần replica; ứng dụng cần chính sách retry/idempotency thích hợp thay vì kết luận dữ liệu chưa được ghi.

## 9. Ba bài thực hành ngắn

### Thực hành A — Kết nối từ máy host

**Giả định:** Cassandra local đang lắng nghe CQL ở `127.0.0.1:9042`.

1. Chạy `cqlsh 127.0.0.1 9042`; nếu chưa kết nối được, kiểm tra server và cổng trước.
2. Thực thi `SELECT data_center, rack FROM system.local;`, ghi lại **tên DC thực tế**.
3. Đặt `spring.cassandra.contact-points`, `port`, `local-datacenter` vào Spring Boot theo kết quả vừa kiểm tra.
4. Kiểm tra khởi tạo kết nối rồi đọc một bảng thử nghiệm với repository hoặc `CassandraTemplate`. Nếu chưa có keyspace, tạo trong môi trường thử nghiệm hoặc dùng keyspace đã chuẩn bị.
5. Ghi lại host, port, DC và thông báo lỗi nếu không thành công.

### Thực hành B — Chuyển ứng dụng từ host vào container

**Giả định:** Spring Boot và Cassandra chuyển sang cùng mạng Docker.

1. Giải thích vì sao `127.0.0.1` trong container ứng dụng không còn là Cassandra.
2. Đổi contact point sang hostname của service Cassandra trong network, ví dụ `cassandra`, với port **9042 nội bộ**.
3. Giữ local DC đúng như node Cassandra đã khai báo; không đổi nó theo tên service.
4. Kiểm tra DNS, kết nối TCP và CQL từ container ứng dụng.
5. Nếu cluster có nhiều node, xác minh các địa chỉ được driver khám phá cũng kết nối được.

### Thực hành C — Chẩn đoán cấu hình sai local DC

**Giả định:** `nodetool status` hiển thị `Datacenter: dc1` nhưng cấu hình Spring Boot đang ghi `local-datacenter: prod`.

1. Dự đoán tác động đến khởi tạo `CqlSession`/lựa chọn node.
2. Xác minh lại bằng `nodetool status` hoặc `system.local`.
3. Sửa local DC thành `dc1`, chạy lại ứng dụng và kiểm tra kết quả.
4. Giải thích vì sao thay đổi này không thay đổi datacenter của node, token range hoặc replication factor.

**Tiêu chí hoàn thành:** người học có thể giải thích và kiểm chứng từng giá trị **contact point / cổng native / local DC** từ môi trường thực tế; phân biệt được lỗi kết nối cơ bản với lỗi CQL/consistency; biết vì sao ứng dụng phải truy cập được cả những node được driver khám phá.

## 10. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “localhost luôn là node Cassandra đầu tiên.” | `localhost` trỏ tới chính nơi chạy tiến trình Spring Boot |
| “9042 là cổng của mọi dịch vụ trong Cassandra.” | 9042 thường dành cho CQL client; internode và JMX dùng cổng/giao thức khác |
| “Khai báo một contact point nghĩa là mọi query chạy trên node đó.” | Driver khám phá cluster và chọn coordinator theo chính sách |
| “Contact points phải trùng Cassandra seed nodes.” | Hai cấu hình phục vụ client và giao tiếp nội bộ khác nhau |
| “Đặt local-datacenter thành tên vùng cloud là đủ.” | Phải dùng **tên DC thực tế** Cassandra quảng bá |
| “Đổi local DC sẽ tự chuyển replica sang DC gần ứng dụng.” | Replication strategy/keyspace của Cassandra quyết định vị trí replica |
| “TCP mở là CQL chắc chắn hoạt động.” | Còn TLS, auth, driver compatibility, metadata và quyền keyspace |
| “Một contact point truy cập được là cả cluster ổn.” | Các địa chỉ node driver khám phá cũng phải có thể kết nối |
| “Repository hoặc CassandraTemplate tự khắc phục mọi vấn đề network.” | Cả hai phụ thuộc `CqlSession` và cluster; cần cấu hình, kiểm thử, quan sát lỗi |

## 11. Câu hỏi tự kiểm tra

1. Contact points được dùng ở giai đoạn nào? Vì sao driver có thể gửi truy vấn tới node không có trong danh sách ban đầu?
2. Khác biệt giữa contact point, seed node, coordinator và replica là gì?
3. Cassandra native transport thường dùng cổng nào? Vì sao 7000 và 7199 không phải lựa chọn mặc định cho CQL?
4. Khi Spring Boot chuyển vào container, địa chỉ `127.0.0.1` có còn trỏ tới Cassandra trên máy host không?
5. Tên local datacenter lấy từ đâu và vì sao không nên đoán bằng tên vùng địa lý hoặc tên ứng dụng?
6. Với keyspace RF = 3 ở `dc1` và `dc2`, cách hiểu `LOCAL_QUORUM` khác gì việc đếm replica trên toàn cluster?
7. Spring Boot 2.x và 3.x có thể dùng cùng prefix cấu hình Cassandra không?
8. Tại sao ứng dụng có thể bắt tay thành công với contact point nhưng thất bại khi driver chọn một node khác?
9. Nếu kiểm tra TCP thành công nhưng CQL không chạy, nên kiểm tra những lớp nào tiếp theo?
10. Khi một truy vấn bị timeout, tại sao chưa nên kết luận là sai contact point hay dữ liệu chắc chắn chưa ghi?

**Ghi nhớ:** cấu hình kết nối đúng bắt đầu từ **địa chỉ node ứng dụng thực sự tiếp cận được**, **cổng CQL native đang mở** và **tên datacenter chính xác của Cassandra**. Sau khi kết nối và discovery thành công, thiết kế partition key, consistency, paging và truy vấn CQL vẫn quyết định tính đúng đắn và hiệu năng của ứng dụng Spring Data Cassandra.
