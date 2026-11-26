# Cổng kết nối, URI, giao thức Bolt và truy cập qua trình duyệt

## 1. Mục tiêu và bối cảnh

Neo4j là hệ quản trị cơ sở dữ liệu theo mô hình **property graph**: **node** biểu diễn thực thể, **relationship** biểu diễn liên kết có hướng và **property** lưu thông tin của chúng. Ta thao tác với đồ thị bằng **Cypher**. Để học tiếp về index, constraint, đường đi, tối ưu truy vấn, nhập dữ liệu hay tích hợp **Java Driver** và **Spring Data Neo4j**, trước hết phải kết nối đúng **DBMS Neo4j**.

Một lỗi rất thường gặp là mở được giao diện web ở cổng `7474` nhưng ứng dụng Java vẫn báo không kết nối được. Lý do là **địa chỉ mở giao diện**, **địa chỉ truy vấn bằng Driver**, **giao thức vận chuyển** và **nơi ứng dụng đang chạy** là những yếu tố khác nhau.

Kết thúc bài này, bạn có thể:

1. Giải thích chức năng các cổng `7474`, `7473` và `7687` cùng cách thay đổi chúng.
2. Đọc và lựa chọn đúng URI dạng `bolt://`, `neo4j://`, `bolt+s://`, `neo4j+s://` và các biến thể TLS.
3. Mở Neo4j Browser, kết nối và kiểm tra database bằng Cypher.
4. Phân biệt `localhost` trên máy host, bên trong Docker container và trên máy khách từ xa.
5. Cấu hình URI cho Java/Spring Boot, xử lý lỗi port, DNS, routing, TLS và xác thực.

**Phạm vi bài:** Ví dụ tập trung vào một Neo4j DBMS cục bộ hoặc container, và đối chiếu với Neo4j AuraDB. Các cổng trong bài là **giá trị thông dụng của cấu hình mặc định**; môi trường thực tế có thể đổi port, interface lắng nghe, giao thức bảo mật hoặc DNS.

## 2. Một kết nối Neo4j thực sự gồm những gì?

Để kết nối, bạn cần biết:

- **Host hoặc IP**: máy/endpoint chạy Neo4j, ví dụ `localhost`, `127.0.0.1`, `neo4j` trong Docker network hoặc hostname do AuraDB cấp.
- **Port**: cổng TCP của dịch vụ tương ứng.
- **Giao thức và bảo mật**: mở giao diện HTTP/HTTPS hay dùng Bolt/Neo4j với hoặc không có TLS.
- **Thông tin xác thực**: thường gồm username, password; phương thức xác thực khác tùy cách triển khai.
- **Database đích**: thường là `neo4j` trên instance thực hành mới, nhưng có thể có tên khác.

Khi dùng Java Driver, các thành phần trên cần khớp **đồng thời**. Kết nối tới đúng port nhưng sai TLS scheme vẫn thất bại; kết nối tới đúng hostname và port nhưng sai mật khẩu cũng không cho phép truy vấn.

### 2.1. Sơ đồ cổng ở môi trường cục bộ

~~~mermaid
flowchart LR
    B["Trình duyệt web"] -->|"HTTP :7474 tải giao diện"| H["HTTP connector"]
    B -->|"Bolt/WebSocket :7687 để truy vấn"| P["Bolt connector"]
    J["Java Driver / cypher-shell"] -->|"Bolt/TCP :7687"| P
    H --> D["Neo4j DBMS"]
    P --> D
    D --> G[("Graph database<br/>node - relationship - property")]
~~~

**Phân biệt hai việc:**

1. Trình duyệt tải **Neo4j Browser** từ HTTP endpoint.
2. Ứng dụng Neo4j Browser sau đó thực hiện kết nối database qua **Bolt**, thường qua WebSocket trong trình duyệt. Vì vậy **tải được trang Browser không chứng minh Bolt port hoạt động**.

Java Driver và `cypher-shell` làm việc với Bolt; **không** đưa `http://localhost:7474` vào cấu hình URI của Java Driver.

## 3. Bảng cổng mặc định và trường hợp sử dụng

| Cổng thông dụng | Giao thức | Vai trò | Cách truy cập |
| --- | --- | --- | --- |
| **7474/TCP** | **HTTP** | Cung cấp Neo4j Browser và HTTP endpoint nếu được bật | `http://localhost:7474/browser/` hoặc `http://localhost:7474` |
| **7473/TCP** | **HTTPS** | HTTP qua TLS, chỉ sử dụng khi **HTTPS connector được bật và cấu hình chứng chỉ** | `https://hostname:7473/browser/` |
| **7687/TCP** | **Bolt** | Kết nối truy vấn từ Java Driver, Spring Data Neo4j, `cypher-shell` và công cụ tương thích | `bolt://localhost:7687` hoặc các URI `neo4j://`, `+s` thích hợp |

Lưu ý:

- **7473 không mặc nhiên được bật** trong mọi cài đặt. HTTPS cần cấu hình TLS/SSL theo phiên bản và môi trường.
- **7687** là cổng Bolt mặc định khi chạy local, **không phải HTTP**. Gõ `http://localhost:7687` vào thanh địa chỉ sẽ không mở Neo4j Browser.
- **443/TCP** thường là HTTPS của web/proxy, **không tự động thay thế 7687** cho Bolt. Với AuraDB, hãy dùng **nguyên URI do Aura Console cung cấp**, thường kết nối TLS tới dịch vụ Bolt qua cổng mặc định của URI.
- Đây là **port listener** trong quá trình Neo4j; Docker có thể ánh xạ một **host port** khác sang container port.
- Không mở các port quản trị hoặc port nội bộ khác ra ngoài chỉ vì muốn truy vấn Cypher. Danh sách cổng bổ sung tùy edition, topology và phiên bản triển khai.

## 4. URI Neo4j và Bolt: nên chọn scheme nào?

Một **URI** gồm ít nhất scheme và hostname, có thể có cổng:

~~~text
scheme://hostname:port
~~~

Ví dụ:

~~~text
bolt://localhost:7687
neo4j://localhost:7687
neo4j+s://example123.databases.neo4j.io
~~~

`example123` chỉ là **instance ID minh họa**. Các URI cần thay bằng endpoint của môi trường thực.

### 4.1. Các scheme thông dụng

| Scheme | Kiểu kết nối | TLS / chứng chỉ | Khi nên dùng |
| --- | --- | --- | --- |
| `bolt://` | Bolt trực tiếp tới host/port chỉ định | Không tự yêu cầu TLS theo scheme | Phát triển local với DBMS đơn lẻ, kết nối trong mạng kiểm soát |
| `neo4j://` | Bolt có **routing**: Driver nhận thông tin máy chủ phù hợp cho phiên làm việc | Không tự yêu cầu TLS theo scheme | Kết nối DBMS/topology cần routing, khi TLS được cấu hình bằng cơ chế phù hợp |
| `bolt+s://` | Bolt trực tiếp | **TLS**, xác minh chứng chỉ theo chuỗi tin cậy hệ thống | Endpoint Bolt trực tiếp có chứng chỉ CA tin cậy |
| `neo4j+s://` | Routing qua Bolt | **TLS**, xác minh chứng chỉ | **AuraDB** và những triển khai có routing + TLS chuẩn |
| `bolt+ssc://` | Bolt trực tiếp | TLS nhưng **chấp nhận chứng chỉ tự ký/không xác minh theo chuỗi tin cậy chuẩn** | Thử nghiệm kiểm soát chặt; không khuyến nghị cho kết nối công cộng/production |
| `neo4j+ssc://` | Routing qua Bolt | TLS với chính sách tin cậy chứng chỉ tự ký tương ứng | Lab có routing và chứng chỉ tự ký khi hiểu rõ rủi ro |

**Quy tắc chọn nhanh:**

- Neo4j cục bộ, chỉ một instance, chưa cấu hình TLS: **`bolt://localhost:7687`**.
- Môi trường Neo4j được quản lý qua **AuraDB**: **URI `neo4j+s://...` lấy từ Aura Console**.
- Cluster, routing hoặc endpoint có nhiều server: dùng **`neo4j://` / `neo4j+s://`** phù hợp với hạ tầng và bảo mật.
- Không đổi `neo4j+s://` thành `bolt://` hay `bolt+ssc://` chỉ để bỏ qua lỗi chứng chỉ. Hãy kiểm tra DNS, TLS, chứng chỉ và cấu hình endpoint.

### 4.2. Bolt trực tiếp và routing khác nhau ở đâu?

**`bolt://`** yêu cầu Driver mở kết nối tới chính địa chỉ chỉ định. Với Neo4j độc lập trên laptop, cách này đơn giản, dễ debug.

**`neo4j://`** cho phép Driver thực hiện **routing discovery**: hỏi server thông tin những địa chỉ thích hợp để đọc/ghi và thiết lập kết nối tới các địa chỉ được quảng bá. Trên hệ thống nhiều server, cơ chế này quan trọng để kết nối đúng vai trò của mỗi server.

~~~mermaid
flowchart TD
    A["Ứng dụng dùng neo4j:// hoặc neo4j+s://"] --> B["Kết nối seed address"]
    B --> C["Nhận routing table"]
    C --> D["Driver kết nối tới advertised address phù hợp"]
    D --> E["Gửi Cypher trong session / transaction"]
~~~

**Hệ quả thực tế:** một kết nối TCP tới seed host có thể thành công, nhưng nếu server quảng bá một địa chỉ **không truy cập được từ ứng dụng** thì Driver dùng routing scheme vẫn thất bại. Lỗi này thường gặp khi DBMS nằm sau NAT, Docker, reverse proxy hoặc trong nhiều mạng khác nhau.

Không phải mọi cấu hình Neo4j Community/standalone đều cần routing. Bài thực hành cục bộ có thể dùng `bolt://` để hạn chế phức tạp.

### 4.3. Hiểu ký hiệu `+s` và `+ssc`

TLS mã hóa lưu lượng và giúp máy khách xác minh server khi dùng chứng chỉ đáng tin cậy.

- `+s`: yêu cầu **TLS** và kiểm tra chứng chỉ của server. Nếu chứng chỉ không hợp lệ, hostname không khớp hoặc CA không được tin cậy, kết nối nên bị từ chối.
- `+ssc`: vẫn mã hóa bằng TLS nhưng nới lỏng việc xác minh chứng chỉ theo hệ thống CA; việc này khiến client dễ bị kết nối tới server giả mạo hơn nếu mạng không đáng tin cậy.
- Không có hậu tố bảo mật: việc mã hóa phụ thuộc cấu hình Driver/server, thường là **không mã hóa** trong các ví dụ cục bộ.

**Chứng chỉ của HTTPS connector và chứng chỉ dùng cho Bolt là hai cấu hình liên quan nhưng không đồng nhất.** Một server có thể phục vụ trang Browser qua HTTPS nhưng Bolt lại chưa được cấu hình TLS. Khi truy cập Browser từ xa bằng HTTPS, chính sách bảo mật của trình duyệt có thể hạn chế kết nối WebSocket không an toàn.

## 5. Phân biệt địa chỉ và phạm vi kết nối

### 5.1. `localhost` luôn chỉ về nơi chương trình đang chạy

| Vị trí chương trình kết nối | `localhost` trỏ đến | URI Bolt thường dùng |
| --- | --- | --- |
| Ứng dụng Java chạy trực tiếp trên laptop, Neo4j publish cổng ra host | **Laptop** | `bolt://localhost:7687` |
| Ứng dụng Java ở **container khác** cùng Compose network với service `neo4j` | **Container Java**, không phải Neo4j | `bolt://neo4j:7687` |
| Java chạy trên một VM/máy khác | **Máy chạy Java** | URI dùng DNS/IP truy cập được của máy Neo4j, theo chính sách mạng/TLS |
| Ứng dụng kết nối AuraDB | Không sử dụng localhost | `neo4j+s://<id>.databases.neo4j.io` do Aura cấp |

`127.0.0.1` là địa chỉ loopback **IPv4**; `localhost` có thể phân giải sang IPv4 hoặc IPv6 tùy hệ điều hành. Khi chẩn đoán một kết nối chỉ nghe IPv4, kiểm tra cụ thể `127.0.0.1` cũng giúp xác định khác biệt DNS/IPv6.

### 5.2. Host port khác container port

Ví dụ trong Docker Compose:

~~~yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    ports:
      - "127.0.0.1:7475:7474"
      - "127.0.0.1:7688:7687"
~~~

Cách đọc `"127.0.0.1:7688:7687"`:

- **127.0.0.1**: chỉ publish trên loopback của host.
- **7688**: port mà **Java chạy trên host** gọi đến.
- **7687**: port Bolt **bên trong container**, dành cho các ứng dụng cùng Docker network.

Với cấu hình này:

~~~text
Trình duyệt trên host:        http://localhost:7475/browser/
Java Driver trên host:        bolt://localhost:7688
Java trong cùng Compose:      bolt://neo4j:7687
~~~

Không dùng `bolt://neo4j:7688` từ container Java trong cùng Compose network, vì `7688` là port publish trên **host**, không phải port của service.

### 5.3. Địa chỉ lắng nghe và địa chỉ công bố

Neo4j phân biệt:

- **Listen address**: interface/port mà DBMS mở để nhận kết nối, ví dụ `0.0.0.0:7687` trong container.
- **Advertised address**: địa chỉ mà DBMS thông báo cho Driver hoặc các thành phần khác để kết nối, đặc biệt quan trọng với routing.

Một số tên cấu hình Neo4j 5.x/2026.x liên quan:

~~~properties
# Vi du minh hoa neo4j.conf, KHONG tu dong them vao moi may
server.bolt.enabled=true
server.bolt.listen_address=:7687
server.http.enabled=true
server.http.listen_address=:7474
~~~

Các thiết lập như `server.default_listen_address` và `server.bolt.advertised_address` có thể cần điều chỉnh khi chạy sau NAT/proxy hoặc nhiều host; **không** tự đặt địa chỉ công bố bằng `localhost` nếu ứng dụng chạy ở máy khác.

**Chú ý:** `0.0.0.0` dùng cho **bind/listen** trên mọi IPv4 interface, không phải hostname hợp lệ để máy khách dùng kết nối đến máy chủ ở xa. Khi cấu hình network từ xa, hãy dùng địa chỉ DNS/IP thực và thiết kế firewall, TLS, xác thực đúng mức.

## 6. Bài thực hành: Neo4j cục bộ bằng Docker Compose

Ví dụ sau chỉ nhằm tạo **một database kiểm thử** để quan sát cổng và URI. Nếu đã có Neo4j trên host, bạn có thể giữ nguyên DBMS hiện tại và chuyển tới mục 7.

Tạo `compose.yaml` trong một thư mục lab riêng:

~~~yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD:?Set NEO4J_PASSWORD in .env}"
    volumes:
      - neo4j_data:/data

volumes:
  neo4j_data:
~~~

Tạo `.env` **trong cùng thư mục**:

~~~dotenv
NEO4J_PASSWORD=REPLACE_WITH_A_UNIQUE_STRONG_PASSWORD
~~~

Thay placeholder bằng mật khẩu thật dành riêng cho **lab cục bộ** trước khi chạy. Không commit `.env` vào Git; thêm nó vào `.gitignore`. Cấu hình này giúp minh họa giao thức/cổng, nhưng `.env` không phải secret manager; với dự án nhóm/production hãy dùng cơ chế quản lý secret như **Compose secrets** và tùy chọn `NEO4J_AUTH_FILE` được Neo4j Docker hỗ trợ.

> **Quan trọng:** `NEO4J_AUTH` đặt mật khẩu **khởi tạo lần đầu** cho cơ sở dữ liệu nằm trong volume trống. Nếu volume `neo4j_data` đã có dữ liệu, sửa mật khẩu trong `.env` rồi chạy lại Compose **không đặt lại mật khẩu cũ**.

Kiểm tra và khởi động:

~~~bash
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Chờ log báo DBMS đã sẵn sàng. Nếu `7474` hoặc `7687` bị chiếm, đổi **host port** trong `ports`, rồi thay URI trong các bước dưới đây cho tương ứng. Không cần đổi port Neo4j bên trong container chỉ vì host port xung đột.

**Dữ liệu lưu tại named volume `neo4j_data`**. Lệnh `docker compose down` giữ volume mặc định; `docker compose down -v` xóa volume của project và có thể khiến mất toàn bộ dữ liệu lab.

## 7. Truy cập qua Neo4j Browser

**Neo4j Browser** là công cụ web giúp viết Cypher, xem kết quả dạng bảng hoặc đồ thị và thực hiện truy vấn trên database. Nó không phải một database riêng.

### 7.1. Mở giao diện và thiết lập kết nối

1. Với ví dụ cục bộ ở mục 6, mở **`http://localhost:7474/browser/`** (hoặc `http://localhost:7474` và theo redirect nếu có).
2. Trong màn hình kết nối của Browser, dùng **URI** `bolt://localhost:7687` khi môi trường local không bật TLS.
3. Nhập **username `neo4j`** và mật khẩu đã thiết lập cho đúng instance.
4. Chọn **Connect**. Nếu Browser yêu cầu đổi mật khẩu ban đầu, hoàn tất và cập nhật credential dùng cho ứng dụng.
5. Chạy truy vấn kiểm tra bằng ô lệnh Cypher:

~~~cypher
RETURN 1 AS ok, datetime() AS serverTime;
~~~

Kết quả dự kiến gồm `ok = 1` và thời gian do database trả về. Nếu trang Browser tải được nhưng kết nối báo lỗi, kiểm tra **Bolt URI, port, TLS và credential** trước khi cài lại Neo4j.

### 7.2. Xác định mình đang kết nối tới DBMS nào

Khi máy có nhiều instance hoặc container, tuyệt đối không suy ra server version từ phiên bản Neo4j Browser. Chạy:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Kết quả cho biết **version và edition** của DBMS đang xử lý truy vấn. Nếu có nhiều database và được cấp quyền tương ứng, kiểm tra:

~~~cypher
SHOW DATABASES;
~~~

Các quyền và khả năng quản lý nhiều database phụ thuộc edition/tài khoản. Thông thường lab mới có database tên `neo4j`, nhưng cần xác nhận tên thực thay vì tự mặc định trong mọi môi trường.

### 7.3. Thử đọc một đường đi trong property graph

~~~cypher
MERGE (a:Person {personId: 'neo4j-port-001'})
  ON CREATE SET a.name = 'An'
MERGE (b:Person {personId: 'neo4j-port-002'})
  ON CREATE SET b.name = 'Bình'
MERGE (a)-[:KNOWS]->(b)
RETURN a.name AS sourcePerson, b.name AS targetPerson;
~~~

~~~cypher
MATCH path =
  (:Person {personId: 'neo4j-port-001'})
  -[:KNOWS]->
  (:Person {personId: 'neo4j-port-002'})
RETURN path;
~~~

Neo4j Browser có thể hiển thị `path` dưới dạng đồ thị gồm hai node `Person` và relationship `KNOWS`. `MERGE` giúp tránh tạo trùng mẫu trong lab khi chạy lại; với tải ghi đồng thời trong dự án thật, cần thêm **uniqueness constraint** cho khóa nghiệp vụ và thiết kế transaction phù hợp.

### 7.4. Trường hợp Browser chạy từ một máy khác

Giả sử Neo4j chạy trên máy chủ `db.example.internal`, máy cá nhân chỉ mở giao diện web từ xa. Để hoạt động:

1. HTTP/HTTPS endpoint của Browser phải **có thể truy cập** từ máy cá nhân, thông qua mạng nội bộ/VPN/proxy được cấp phép.
2. **Bolt endpoint** mà Browser dùng cũng phải truy cập được từ máy cá nhân; mở được HTML/JS trên port HTTP chưa đủ.
3. Nếu giao diện chạy qua **HTTPS**, kết nối Bolt/WebSocket phải tuân thủ chính sách TLS của trình duyệt; tránh **mixed content**.
4. Khi dùng `neo4j+s://`, hostname, certificate và **advertised address** (nếu routing) phải hợp lệ và truy cập được.

Không publish trực tiếp Browser HTTP và Bolt ra Internet chỉ để tiện dùng từ xa. Với hệ thống nhiều người dùng, cần đánh giá VPN/reverse proxy, TLS, firewall và quyền truy cập trước.

### 7.5. Neo4j AuraDB

AuraDB là Neo4j được quản lý trên cloud. Từ **[Aura Console](https://console.neo4j.io/)**, chọn instance, dùng **Query** hoặc công cụ truy vấn được cung cấp, lấy **Connection URI**, username và password. URI thường có dạng:

~~~text
neo4j+s://example123.databases.neo4j.io
~~~

Không mở `http://localhost:7474` nếu bạn chỉ có AuraDB và chưa cài Neo4j local. Với AuraDB, hãy **sao chép nguyên URI từ console** và dùng TLS theo hướng dẫn; không tự đặt địa chỉ HTTP hay tên DNS từ ví dụ. Nếu AuraDB Free tạm dừng vì không hoạt động, cần kiểm tra trạng thái trong Aura Console trước khi chẩn đoán DNS/TLS.

## 8. Kiểm tra bằng Cypher Shell và Java Driver

### 8.1. Cypher Shell: tách giao diện Browser khỏi kết nối Bolt

Nếu môi trường có sẵn `cypher-shell`, thử kết nối trực tiếp bằng Bolt:

~~~bash
# Chay tren host neu da cai cypher-shell va Neo4j publish port 7687
cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j
~~~

Nếu bạn dùng container Docker ở mục 6, có thể chạy:

~~~bash
docker compose exec neo4j cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j
~~~

Khi được hỏi, nhập mật khẩu đúng của database. **Không truyền password trực tiếp vào tham số `-p`** trên máy dùng chung nếu có thể tránh được, vì nó có thể xuất hiện trong shell history hoặc danh sách tiến trình.

Sau khi kết nối, chạy:

~~~cypher
RETURN 'Bolt OK' AS status;
~~~

Nếu Cypher Shell kết nối được nhưng Browser vẫn lỗi, tập trung kiểm tra **địa chỉ Browser, WebSocket, trình duyệt, TLS và cài đặt phía client**. Nếu cả hai đều thất bại, kiểm tra DBMS, cổng Bolt và xác thực.

### 8.2. Cấu hình Spring Data Neo4j

Trong ứng dụng Spring Boot có dependency tương thích với Neo4j/Spring Data Neo4j, dùng `application.properties`:

~~~properties
spring.neo4j.uri=${NEO4J_URI}
spring.neo4j.authentication.username=${NEO4J_USERNAME}
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

Thiết lập biến môi trường theo vị trí ứng dụng:

| Ứng dụng Spring Boot chạy ở đâu? | `NEO4J_URI` ví dụ |
| --- | --- |
| Trên host, Neo4j Docker publish `7687` | `bolt://localhost:7687` |
| Trong service khác cùng Compose network | `bolt://neo4j:7687` |
| Trên host, Neo4j Docker publish host port `7688` | `bolt://localhost:7688` |
| Kết nối AuraDB | URI `neo4j+s://...` do Aura Console cấp |

Credential phải thuộc **đúng DBMS/instance**; không mặc định Docker secret của service Neo4j cũng được chia sẻ cho container ứng dụng Spring Boot.

### 8.3. Kiểm tra với Neo4j Java Driver

Đoạn Java dưới đây minh họa logic kết nối (cần dependency **Neo4j Java Driver** tương thích với JDK ứng dụng và phiên bản Neo4j Server):

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;

public class Neo4jConnectionCheck {
    public static void main(String[] args) {
        String uri = System.getenv("NEO4J_URI");
        String username = System.getenv("NEO4J_USERNAME");
        String password = System.getenv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(username, password))) {
            driver.verifyConnectivity();
            try (Session session = driver.session()) {
                int value = session.run("RETURN 1 AS ok")
                                   .single().get("ok").asInt();
                System.out.println("Neo4j connected: " + value);
            }
        }
    }
}
~~~

Kết quả mong đợi: `Neo4j connected: 1`. Trong ứng dụng thật, hãy chọn **database** rõ ràng khi cần, quản lý Driver theo vòng đời ứng dụng và bổ sung timeout/retry thích hợp. Không ghi mật khẩu vào log hay hardcode trong source.

**Lưu ý phiên bản:** JVM của ứng dụng Java và JVM của Neo4j Server có thể khác nhau vì hai tiến trình độc lập; điều cần kiểm tra là ma trận tương thích **Java Driver ↔ JDK ứng dụng ↔ Neo4j Server**.

## 9. Kiểm tra cổng và xử lý sự cố theo tầng

### 9.1. Bước 1 — DBMS có hoạt động không?

Với Docker:

~~~bash
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Với Neo4j Desktop, kiểm tra trạng thái DBMS và log trong giao diện. Với server native trên Linux, xem trạng thái dịch vụ và log theo hệ thống đang dùng, chẳng hạn `systemctl status neo4j`.

**Container running chưa chắc DBMS đã sẵn sàng nhận Cypher**: cần chờ startup, đọc log hoặc thực hiện kiểm tra truy vấn.

### 9.2. Bước 2 — Máy khách có tới đúng port không?

Kiểm tra HTTP (host Linux/macOS):

~~~bash
curl -I http://127.0.0.1:7474
~~~

Nhận được HTTP response cho biết HTTP connector có thể truy cập, **không phải bằng chứng Bolt hoạt động**.

Kiểm tra TCP Bolt trên Linux/macOS (nếu đã cài `nc`):

~~~bash
nc -vz 127.0.0.1 7687
~~~

Kiểm tra trên Windows PowerShell:

~~~powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 7687
~~~

`TcpTestSucceeded = True` hoặc `nc` báo connected chỉ chứng minh **TCP đi tới được cổng**; vẫn phải xác minh đúng giao thức, TLS, user và database.

Nếu host báo port xung đột, trên Linux có thể xem:

~~~bash
ss -lnt
~~~

Trên Windows PowerShell:

~~~powershell
Get-NetTCPConnection -State Listen -LocalPort 7474,7687 -ErrorAction SilentlyContinue
~~~

Nếu đang ở trong container ứng dụng, lệnh kiểm tra phải chạy **từ chính container/network đó**. Một kết nối thành công trên host không đủ để kết luận container khác phân giải được hostname `neo4j`.

### 9.3. Bước 3 — Kiểm tra URI, routing, TLS và xác thực

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Connection refused` ngay khi mở Driver | Port sai, DBMS chưa lắng nghe, chưa publish, sai hostname | Kiểm tra tiến trình/log và port từ **nơi chương trình chạy** |
| Browser tải trang được nhưng báo không kết nối database | HTTP OK nhưng Bolt/WebSocket không thông, sai URI hoặc credential | Thử `cypher-shell`, kiểm tra `7687`, URI và log |
| Driver trong container dùng `localhost` bị từ chối | `localhost` trỏ về container ứng dụng | Với cùng Compose network, dùng `bolt://neo4j:7687` |
| `Unable to retrieve routing information` hoặc lỗi routing table | Server trả địa chỉ công bố không tới được hoặc cấu hình routing/network sai | Đối chiếu DNS, **advertised address** và dùng routing URI đúng topology |
| TLS handshake/certificate error | Dùng sai scheme, hostname không khớp, thiếu CA, endpoint không hỗ trợ TLS | Dùng URI chính thức; kiểm tra chứng chỉ/CA và cấu hình TLS |
| `Authentication failed` | Sai user/password, instance khác hoặc mật khẩu trong volume cũ | Xác minh instance/port và credential; đổi mật khẩu bằng công cụ quản trị |
| `Database not found` / không đủ quyền | Sai tên database hoặc quyền truy cập | Xác minh database và quyền tài khoản |
| `curl` vào `http://localhost:7687` thất bại | Dùng HTTP để thử cổng Bolt | Kiểm tra TCP hoặc dùng công cụ **Bolt** như `cypher-shell` |
| Java kết nối local được, từ máy khác không được | Host chỉ bind `127.0.0.1`, firewall hoặc DNS | Thiết kế endpoint từ xa đúng mạng và TLS; không mở public tùy tiện |
| AuraDB không kết nối sau thời gian không dùng | Instance pause, sai URI, network chặn Bolt/TLS | Kiểm tra Aura Console, URI chính thức và firewall/DNS |

**Thứ tự xử lý hiệu quả:** xác định **nơi client chạy** → hostname/DNS → TCP port → HTTP hay Bolt → routing/TLS → credential → database/quyền → truy vấn Cypher.

## 10. An toàn khi mở cổng và kết nối từ xa

Một cấu hình chạy được trên laptop chưa đủ an toàn khi chuyển ra Internet:

- Giữ `7474`/`7687` **chỉ bind loopback** cho lab cục bộ, ví dụ `127.0.0.1:7687:7687` trong Docker Compose.
- Khi kết nối từ xa, ưu tiên **mạng riêng/VPN hoặc endpoint được bảo vệ**, firewall giới hạn nguồn truy cập và **TLS** với chứng chỉ được xác minh.
- **Không dùng `bolt+ssc://` để bỏ qua kiểm tra chứng chỉ** trên mạng công cộng. Với AuraDB, luôn dùng URI `neo4j+s://` do dịch vụ cấp.
- Đặt mật khẩu mạnh, phân quyền theo nguyên tắc cần thiết; tài khoản quản trị không nên được tái sử dụng vô hạn cho mọi ứng dụng.
- Bảo vệ credential trong secret manager hoặc cơ chế secret phù hợp, không đưa vào Git, log, tài liệu thực hành hoặc command history.
- Thay đổi `listen_address`/`advertised_address` chỉ khi đã hiểu **các đường đi mạng** của client; thông báo địa chỉ nội bộ cho client bên ngoài có thể làm routing thất bại.

## 11. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Phân biệt hai cổng

Neo4j cục bộ đã chạy, bạn mở được `http://localhost:7474/browser/` nhưng Java Driver dùng `http://localhost:7474` và báo lỗi. Hãy chỉ ra lỗi giao thức, chọn URI đúng và giải thích vì sao Browser UI vẫn hoạt động.

**Đáp án định hướng:** Java Driver sử dụng Bolt, ví dụ `bolt://localhost:7687`; `7474` là HTTP connector.

### Bài tập 2 — Đổi host port trong Compose

Thay `127.0.0.1:7687:7687` bằng `127.0.0.1:7688:7687`. Xác định URI khi Java chạy trên host và khi Java chạy trong container khác cùng Compose network. Thử `cypher-shell` từ host/container nếu có và đối chiếu kết quả.

**Đáp án định hướng:** host dùng `bolt://localhost:7688`, container cùng network dùng `bolt://neo4j:7687`.

### Bài tập 3 — Phân tích TLS trên AuraDB

Một ứng dụng được cung cấp `neo4j+s://example123.databases.neo4j.io` nhưng lập trình viên sửa thành `bolt://example123.databases.neo4j.io` để “giảm lỗi cấu hình”. Chỉ ra rủi ro và trình bày các bước kiểm tra đúng khi chứng chỉ/TLS thất bại.

**Đáp án định hướng:** giữ nguyên URI từ Aura Console; kiểm tra DNS, mạng/port, CA/certificate và trạng thái instance, không tắt TLS.

### Bài tập 4 — Routing và advertised address

Client truy cập được seed hostname bằng TCP nhưng Driver với `neo4j://` báo không lấy được routing information hoặc không kết nối được các server được quảng bá. Giải thích vì sao kết nối seed thành công chưa đủ, và cần đối chiếu thông tin địa chỉ nào.

**Đáp án định hướng:** kiểm tra routing table, advertised address và khả năng truy cập các endpoint đó **từ mạng của client**.

### Checklist hoàn thành

- [ ] Phân biệt được HTTP `7474`, HTTPS `7473` tùy cấu hình và Bolt `7687`.
- [ ] Phân biệt Browser UI với kết nối database thực hiện qua Bolt.
- [ ] Chọn `bolt://` cho lab đơn lẻ và `neo4j+s://` từ AuraDB khi phù hợp.
- [ ] Biết khác biệt `+s` và `+ssc`, không tùy tiện bỏ xác thực chứng chỉ.
- [ ] Biết `localhost` trong container Java không phải Neo4j container.
- [ ] Kiểm tra `CALL dbms.components()` và chạy được Cypher đọc một đường đi.
- [ ] Phân biệt TCP port reachable với xác thực DBMS thành công.
- [ ] Biết cách chẩn đoán routing/advertised address và không mở cổng public tùy tiện.

## 12. Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Configuration: Ports](https://neo4j.com/docs/operations-manual/current/configuration/ports/) — vai trò và cổng kết nối.
- [Neo4j Operations Manual — Connectors](https://neo4j.com/docs/operations-manual/current/configuration/connectors/) — HTTP, HTTPS, Bolt; listen/advertised address.
- [Neo4j Operations Manual — SSL framework](https://neo4j.com/docs/operations-manual/current/security/ssl-framework/) — chứng chỉ và thiết lập TLS.
- [Neo4j Browser Manual](https://neo4j.com/docs/browser-manual/current/) — sử dụng Browser và kết nối database.
- [Neo4j Java Driver — Connect to the database](https://neo4j.com/docs/java-manual/current/connect/) — Driver URI, xác thực, kiểm tra kết nối.
- [Neo4j Operations Manual — Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/) — publish port và khởi chạy DBMS.
- [Neo4j Aura — Connect to an instance](https://neo4j.com/docs/aura/getting-started/connect-instance/) — URI và credential cho AuraDB.

**Ghi nhớ:** Đọc URI từ góc nhìn **chương trình đang kết nối**. Khi truy vấn Neo4j, cần đồng thời đúng **địa chỉ, port, Bolt/routing scheme, TLS, credential và database**. Kiểm tra từng lớp sẽ tìm ra vấn đề nhanh hơn việc thử ngẫu nhiên các URI.
