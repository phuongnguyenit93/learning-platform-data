# Lựa chọn môi trường cục bộ, Docker và dịch vụ Neo4j Aura

## 1. Mục tiêu và bối cảnh

Neo4j là hệ quản trị cơ sở dữ liệu đồ thị theo mô hình **property graph**. Dữ liệu được biểu diễn bằng **node** (đỉnh), **relationship** (cạnh có hướng và kiểu) và **property** (thuộc tính). Ta truy vấn node, quan hệ và đường đi bằng **Cypher**. Trước khi học mô hình hóa, index, constraint, tối ưu truy vấn, nhập dữ liệu hoặc kết nối bằng Java Driver và Spring Data Neo4j, cần chọn được môi trường chạy phù hợp.

Sau bài học, bạn có thể:

- Phân biệt cài Neo4j cục bộ, chạy bằng Docker và dùng dịch vụ được quản lý **Neo4j AuraDB**.
- Chọn môi trường dựa trên mục tiêu học, khả năng làm việc ngoại tuyến, mức độ kiểm soát và yêu cầu triển khai.
- Khởi tạo một DBMS Neo4j, xác định địa chỉ truy cập, thiết lập tài khoản và chạy Cypher kiểm tra.
- Hiểu cách giữ dữ liệu, quản lý mật khẩu và xử lý một số lỗi kết nối thường gặp.
- Chuẩn bị các thông số kết nối dùng lại cho ứng dụng Java hoặc Spring Boot.

> **Phạm vi:** Bài này tập trung vào việc chọn và dựng môi trường ban đầu. Triển khai cluster, hardening cho production, lập kế hoạch backup, tuning bộ nhớ và các tính năng của bản Enterprise cần tài liệu vận hành chuyên sâu riêng.

## 2. Ba lựa chọn đang giải quyết những nhu cầu nào?

Ba cách chạy Neo4j đều cho phép học Cypher và làm việc với property graph, nhưng khác nhau ở nơi DBMS hoạt động và ai chịu trách nhiệm vận hành.

| Tiêu chí | Cục bộ: Neo4j Desktop / server | Docker trên máy phát triển | Neo4j AuraDB |
| --- | --- | --- | --- |
| DBMS chạy ở đâu? | Trên hệ điều hành máy cá nhân | Trong container trên máy/host bạn quản lý | Trên hạ tầng cloud do Neo4j quản lý |
| Cài đặt ban đầu | Qua giao diện Desktop hoặc cài gói server | Cài Docker Engine/Desktop, khai báo image và volume | Tạo tài khoản, tạo instance trên Aura Console |
| Làm việc khi mất Internet | Có, sau khi đã tải và cài đủ thành phần | Có, nếu image đã tải sẵn | Không; cần kết nối đến dịch vụ |
| Quyền cấu hình hệ thống | Tùy edition, thường khá linh hoạt | Rõ ràng, dễ mô tả bằng file Compose | Giới hạn trong tùy chọn dịch vụ cung cấp |
| Độ lặp lại giữa thành viên/CI | Phụ thuộc thao tác và phiên bản cài | Cao nếu pin image, Compose và cấu hình | Cao ở mức ứng dụng, nhưng phụ thuộc trạng thái/tier của dịch vụ |
| Lưu trữ dữ liệu | Thư mục DBMS cục bộ | Volume hoặc bind mount | Dịch vụ quản lý; khả năng backup tùy tier |
| Tài nguyên và chi phí | CPU/RAM/đĩa và thời gian quản trị của bạn | CPU/RAM/đĩa, tài nguyên Docker | Free cho nhu cầu học; tier trả phí theo điều kiện hiện hành |
| Tình huống tiêu biểu | Học cá nhân, thử Cypher, debug | Phát triển ứng dụng, chia sẻ cấu hình nhóm, test tích hợp | Demo từ nhiều máy, POC trên cloud, dịch vụ được quản lý |

**Chọn nhanh theo mục tiêu:**

1. **Mới học và muốn nhìn thấy dữ liệu ngay:** chọn Neo4j Desktop nếu có máy đủ tài nguyên.
2. **Đang làm backend Java/Spring Boot, cần môi trường tái tạo được:** chọn Docker Compose.
3. **Không muốn tự quản lý DBMS, cần truy cập qua Internet:** chọn AuraDB Free để học hoặc chọn tier trả phí phù hợp mục tiêu triển khai.
4. **Cần thay đổi sâu cấu hình, plugin, dữ liệu trên đĩa hoặc kiểm thử vận hành:** ưu tiên môi trường tự quản lý; kiểm tra quyền theo edition.
5. **Hướng đến production:** đánh giá thêm SLA, bảo mật, backup/restore, monitoring, khả năng mở rộng và chi phí; bài học trên một instance không đại diện cho kiến trúc production.

~~~mermaid
flowchart TD
    A["Bạn cần chạy Neo4j"] --> B{"Cần hoạt động ngoại tuyến<br/>hoặc kiểm soát DBMS?"}
    B -- "Không" --> C["AuraDB: dịch vụ được quản lý"]
    B -- "Có" --> D{"Cần môi trường lập lại<br/>bằng cấu hình và CI?"}
    D -- "Có" --> E["Docker + Compose"]
    D -- "Không" --> F["Neo4j Desktop / server cục bộ"]
~~~

## 3. Kiến thức kết nối chung cần nhớ

Một môi trường Neo4j tối thiểu gồm **DBMS đang chạy**, **cơ sở dữ liệu (database)**, **thông tin xác thực** và **địa chỉ kết nối**. Không nên nhầm DBMS (quản lý một hoặc nhiều database, tùy edition) với từng database chứa node/relationship.

| Thành phần | Giá trị thường gặp | Mục đích |
| --- | --- | --- |
| HTTP / Neo4j Browser | `http://localhost:7474` | Dùng giao diện để chạy truy vấn trên máy cục bộ |
| Bolt | `bolt://localhost:7687` | Kết nối trực tiếp từ Driver tới Neo4j đơn lẻ, thường dùng khi phát triển cục bộ |
| Routing scheme | `neo4j://...` | Cho phép Driver sử dụng thông tin định tuyến do DBMS trả về khi phù hợp |
| AuraDB qua Bolt có TLS | `neo4j+s://<instance-id>.databases.neo4j.io` | Kết nối mã hóa và xác thực chứng chỉ tới AuraDB |
| Username ban đầu | `neo4j` | Tài khoản mặc định thường gặp |
| Database | Thường là `neo4j` | Database được chọn để thực thi Cypher; xác nhận tên thực tế trong instance |

**Phân biệt giao diện và giao thức:** địa chỉ `http://localhost:7474` mở giao diện web; Java Driver kết nối qua URI Bolt/Neo4j phù hợp, không dùng địa chỉ giao diện web để khởi tạo Bolt Driver. Cổng `7474` và `7687` chỉ là mặc định của cài đặt cục bộ, có thể được cấu hình lại.

Trong ví dụ, mật khẩu và instance ID chỉ là **giá trị minh họa**. Không đưa mật khẩu, credential download từ Aura hoặc file `.env` chứa bí mật vào Git.

## 4. Phương án A — Chạy Neo4j trên máy cục bộ

### 4.1. Neo4j Desktop: thuận tiện cho người mới

Neo4j Desktop cung cấp giao diện tạo và quản lý DBMS trên máy cá nhân, khởi động/dừng server, quản lý kết nối và mở công cụ truy vấn. Desktop 2.x cũng có thể kết nối tới DBMS từ xa. Giấy phép Developer Edition đi kèm Desktop được dành cho **phát triển**, không mặc nhiên cho phép sử dụng như một bản Enterprise production.

Các bước:

1. Tải và cài **Neo4j Desktop** từ trang chính thức; chọn bản tương thích hệ điều hành và kiến trúc CPU.
2. Trong Desktop, tạo một DBMS cục bộ; chọn phiên bản DBMS tương thích với khóa học/dự án.
3. Đặt mật khẩu đủ mạnh cho người dùng `neo4j` và lưu ở trình quản lý bí mật cá nhân.
4. Khởi động DBMS; chờ trạng thái cho biết server đã sẵn sàng.
5. Mở công cụ Query/Browser từ Desktop, đăng nhập bằng tài khoản của DBMS, sau đó chạy:

~~~cypher
RETURN 'Neo4j local ready' AS message, 1 + 1 AS result;
~~~

Kết quả dự kiến có một dòng với `message = "Neo4j local ready"` và `result = 2`. Tùy phiên bản Desktop, tên nút hoặc màn hình có thể khác nhau; hãy tìm mục quản lý DBMS và công cụ Query.

**Ưu điểm:** ít phải nhớ lệnh, dễ xem log và cấu hình, hữu ích khi học cú pháp Cypher và quan sát đồ thị. **Giới hạn:** việc tạo DBMS thủ công không bảo đảm mọi thành viên đều dùng cùng phiên bản/cấu hình; DBMS tiêu thụ tài nguyên máy và cần tự quản lý dữ liệu.

### 4.2. Cài Neo4j server trực tiếp: khi cần kiểm soát hệ điều hành

Ngoài Desktop, có thể cài gói Neo4j Server tương thích với hệ điều hành. Trình tự khái quát:

1. Chọn edition/phiên bản và kiểm tra yêu cầu Java/runtime trong tài liệu của **chính phiên bản đó**.
2. Cài server, thiết lập cấu hình trong `neo4j.conf` và đặt mật khẩu ban đầu theo hướng dẫn phát hành.
3. Khởi động bằng service manager hoặc lệnh `neo4j console` từ thư mục `bin` của gói phân phối (cú pháp/đường dẫn phụ thuộc cách cài).
4. Kiểm tra log và truy cập Browser/Driver qua endpoint đã cấu hình.

Phương án này phù hợp khi cần học hệ điều hành, quyền file, service, cấu hình lưu trữ và log. Đổi lại, việc nâng cấp, sao lưu, cập nhật bảo mật và quản lý tiến trình thuộc trách nhiệm của người vận hành.

## 5. Phương án B — Chạy Neo4j với Docker Compose

Docker đóng gói Neo4j vào image. Compose mô tả cách chạy container, port, environment và volume trong một tệp có thể dùng chung giữa thành viên dự án.

### 5.1. Điều kiện trước khi bắt đầu

- Docker Engine hoặc Docker Desktop đã hoạt động.
- Docker Compose v2 sẵn sàng (lệnh `docker compose`).
- Máy có đủ RAM, CPU và dung lượng đĩa cho DBMS và Docker.
- Host chưa có dịch vụ khác chiếm các port sẽ publish.

Kiểm tra:

~~~bash
docker --version
docker compose version
~~~

Nếu báo không kết nối được Docker daemon, hãy khởi động Docker Desktop/Engine trước khi tiếp tục.

### 5.2. Tạo cấu hình dùng cho môi trường phát triển

Trong một thư mục thực hành riêng, tạo file `compose.yaml`:

~~~yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    environment:
      NEO4J_AUTH: "neo4j/${NEO4J_PASSWORD}"
    volumes:
      - neo4j_data:/data
    restart: unless-stopped

volumes:
  neo4j_data:
~~~

Tạo file `.env` **trong cùng thư mục**:

~~~dotenv
NEO4J_PASSWORD=CHANGE_ME_to_a_unique_strong_password
~~~

Đổi chuỗi mẫu thành mật khẩu riêng của bạn, tránh khoảng trắng/chuỗi gây khó khăn khi nội suy biến nếu chưa hiểu cách Compose phân tích `.env`. Thêm `.env` vào `.gitignore` và dùng phương pháp quản lý secret được phê duyệt khi triển khai thực tế. File `.env` trong ví dụ giúp tránh đặt mật khẩu trực tiếp trong `compose.yaml`, nhưng **không phải kho bí mật an toàn**: ai đọc được file hoặc thông tin cấu hình container có thể tiếp cận credential. Production cần cơ chế secret phù hợp.

**Giải thích Compose:**

- `image: neo4j:2026.10.2` pin phiên bản cụ thể theo ví dụ tại thời điểm biên soạn, giúp tránh thay đổi ngoài ý muốn khi pull lại. Khi làm dự án khác, chọn phiên bản được hỗ trợ và chủ động nâng cấp; tránh phụ thuộc mù quáng vào tag `latest`.
- Hai dòng `ports` ánh xạ HTTP `7474` và Bolt `7687` từ container ra **loopback 127.0.0.1** trên host, đủ cho thực hành cục bộ.
- `NEO4J_AUTH` cung cấp **mật khẩu khởi tạo** cho tài khoản `neo4j` khi database chưa có thông tin xác thực.
- Named volume `neo4j_data` lưu dữ liệu ngoài vòng đời container; container được thay thế không đồng nghĩa với mất database.
- `restart: unless-stopped` cho phép khởi động lại container theo cơ chế Docker, trừ khi đã dừng chủ động.

### 5.3. Khởi động, kiểm tra và dừng

Mở terminal tại thư mục chứa `compose.yaml`:

~~~bash
docker compose up -d
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Chờ đến khi log cho thấy Neo4j đã sẵn sàng, sau đó mở **http://localhost:7474**, đăng nhập người dùng `neo4j` với mật khẩu trong `.env` và thử:

~~~cypher
RETURN 'Docker ready' AS environment;
~~~

Dùng các lệnh vận hành thường gặp:

~~~bash
# Dừng container nhưng vẫn giữ container và volume
docker compose stop

# Khởi động lại container đã dừng
docker compose start

# Xóa container và network Compose, giữ named volume
docker compose down

# Tạo lại container khi cần (dữ liệu vẫn nằm ở named volume)
docker compose up -d
~~~

**Cẩn thận:** lệnh `docker compose down -v` **xóa cả named volume** do Compose quản lý. Với ví dụ này, dữ liệu đồ thị đang lưu trong volume sẽ bị xóa; chỉ dùng khi chủ đích làm mới môi trường và đã có bản sao lưu cần thiết.

**Tình huống dễ nhầm:** nếu volume `neo4j_data` đã chứa database được khởi tạo, thay đổi `NEO4J_PASSWORD` trong `.env` rồi chạy lại container **không đặt lại mật khẩu đã tồn tại**. Cần đổi mật khẩu qua cơ chế quản trị Neo4j phù hợp với tình trạng DBMS, hoặc dùng một volume mới khi thật sự muốn khởi tạo môi trường thực hành sạch.

### 5.4. Kết nối backend chạy trên host hoặc trong container khác

| Ứng dụng gọi Neo4j ở đâu? | URI thường dùng | Giải thích |
| --- | --- | --- |
| Java/Spring Boot chạy trên laptop | `bolt://localhost:7687` | Đi qua port được publish ra host |
| Java/Spring Boot trong **cùng Compose network** | `bolt://neo4j:7687` | `neo4j` là tên DNS nội bộ của service |
| Một máy khác trong mạng hoặc Internet | Không dùng cấu hình loopback ở ví dụ | Cần thiết kế public/private network, TLS và kiểm soát truy cập riêng |

Ở trong container ứng dụng, `localhost` thường trỏ về **chính container ứng dụng**, không trỏ đến container Neo4j. Đây là nguyên nhân thường gặp của lỗi `Connection refused` trong môi trường Docker.

### 5.5. Mở rộng khi học nhập dữ liệu và vận hành

Ví dụ chỉ mount `/data` để giữ database. Khi học `LOAD CSV` từ file local, có thể phải cấp quyền truy cập vùng import phù hợp hoặc bind mount đường dẫn chứa CSV. Khi học log, cấu hình hoặc plugin, cần thiết kế thêm volume và kiểm tra hướng dẫn của bản Neo4j đang dùng. Không mở port database ra Internet chỉ để tiện nhập CSV; nếu cần chia sẻ dữ liệu hãy chọn cơ chế truyền dữ liệu và xác thực phù hợp.

## 6. Phương án C — Neo4j AuraDB trên cloud

**Neo4j AuraDB** là dịch vụ database đồ thị do Neo4j quản lý. Bạn tập trung vào mô hình dữ liệu, Cypher và kết nối ứng dụng; nhiều tác vụ hạ tầng như cấp phát instance và cập nhật hệ thống được dịch vụ xử lý.

### 6.1. Khi nào dùng AuraDB Free hoặc tier trả phí?

**AuraDB Free** phù hợp để học, demo, thử nghiệm mô hình và ứng dụng nhỏ; không cần tự cấp phát CPU/RAM trên laptop. Dịch vụ Free có giới hạn tài nguyên, tính năng và chính sách tạm dừng khi không hoạt động. Theo thông tin sản phẩm hiện hành, Free không có tính năng backup tự động như các tier trả phí và có thể tự pause sau một thời gian không dùng; cần kiểm tra chính sách mới nhất trước khi thiết kế quy trình. Không nên coi Free như một dịch vụ production có SLA.

Tier trả phí phù hợp khi cần dung lượng, độ sẵn sàng, khả năng giám sát, phục hồi và yêu cầu thương mại cao hơn. Hãy xác nhận giới hạn/tính năng cụ thể trong bảng giá và tài liệu Aura tại thời điểm lựa chọn.

### 6.2. Tạo một AuraDB instance

1. Truy cập **[Aura Console](https://console.neo4j.io/)** và đăng nhập hoặc tạo tài khoản.
2. Chọn tạo **AuraDB** instance, chọn tier phù hợp (có thể bắt đầu với Free nếu còn suất).
3. Đặt tên instance, chọn các tùy chọn có sẵn cho tier và tạo database.
4. **Lưu/download credential ngay khi được cung cấp**; mật khẩu tạo ban đầu không thể xem lại nguyên bản nếu đã mất.
5. Sao chép **Connection URI**, **username**, **database name** nếu có và lưu password trong kho bí mật. Ví dụ URI:

~~~text
neo4j+s://example123.databases.neo4j.io
~~~

`example123` là placeholder, không phải instance thực. Khi một tổ chức sử dụng endpoint tùy chỉnh/private networking, hãy lấy **nguyên URI** được Aura Console cấp; không đoán hostname.

### 6.3. Kiểm tra từ giao diện và từ ứng dụng

- Trong Aura Console, mở **Query** hoặc công cụ truy vấn được cung cấp, chọn đúng instance và kết nối bằng credential.
- Chạy `RETURN 'Aura ready' AS environment;` để xác nhận database trả kết quả.
- Khi tích hợp Java Driver hoặc Spring Data Neo4j, dùng URI `neo4j+s://...` do Aura cấp cùng tài khoản/mật khẩu. Hậu tố `+s` yêu cầu TLS với xác thực chứng chỉ; **không đổi thành `bolt://` hoặc vô hiệu hóa kiểm tra chứng chỉ để xử lý lỗi kết nối**.
- Khi instance có nhiều database, chọn đúng database name. Nếu bỏ qua, driver có thể dùng database mặc định của tài khoản/instance.

Mô hình đường đi của truy vấn:

~~~mermaid
flowchart LR
    A["Ứng dụng Java / Spring Boot"] -->|"Bolt / TLS qua Internet"| B["AuraDB instance"]
    C["Aura Query"] --> B
    B --> D["Node + Relationship + Property"]
~~~

**Lưu ý riêng về AuraDB Free:** nếu URI không phân giải được tên miền hoặc kết nối bỗng thất bại sau thời gian không sử dụng, kiểm tra trạng thái **Paused** trong Aura Console và resume nếu cần, rồi mới kiểm tra firewall/DNS.

## 7. Kiểm chứng bằng cùng một bài thử property graph

Để so sánh công bằng ba môi trường, hãy thực hiện cùng thao tác trong một **database thử nghiệm**. Đầu tiên xác minh kết nối:

~~~cypher
RETURN 1 AS ok, datetime() AS serverTime;
~~~

Tiếp theo, tạo một sinh viên, một khóa học và quan hệ đăng ký bằng Cypher:

~~~cypher
MERGE (student:Student {studentId: 'ST-001'})
  ON CREATE SET student.name = 'An'
MERGE (course:Course {courseId: 'NEO4J-101'})
  ON CREATE SET course.title = 'Nhập môn Neo4j'
MERGE (student)-[:ENROLLED_IN]->(course)
RETURN student.name AS studentName, course.title AS courseTitle;
~~~

Đọc lại đường đi:

~~~cypher
MATCH p = (:Student {studentId: 'ST-001'})
          -[:ENROLLED_IN]->
          (:Course {courseId: 'NEO4J-101'})
RETURN p;
~~~

**Giải thích kết quả:**

- `Student` và `Course` là label của node; `studentId`, `courseId`, `name`, `title` là property.
- `ENROLLED_IN` là loại relationship từ sinh viên tới khóa học.
- `MERGE` tìm hoặc tạo mẫu tương ứng, giúp chạy lại ví dụ ít tạo bản sao hơn so với `CREATE` trong bộ dữ liệu thử nghiệm này. Với dữ liệu thực và truy cập đồng thời, vẫn cần thiết kế **uniqueness constraint** phù hợp.
- `MATCH p = ... RETURN p` lấy về một đường đi để Neo4j Browser/Query có thể hiển thị dạng đồ thị.

Để xác minh cơ chế **lưu dữ liệu**, hãy dừng rồi khởi động lại DBMS/container, hoặc đóng phiên làm việc và truy cập lại Aura; chạy lại truy vấn `MATCH`. Nếu trả về đường đi cũ, bạn đã xác nhận dữ liệu nằm trong database, không chỉ tồn tại trong phiên trình duyệt. Trong Docker, phép thử này đặc biệt giúp kiểm tra cấu hình volume.

## 8. Chuẩn bị kết nối cho Java Driver và Spring Data Neo4j

Ứng dụng Java không cần biết bạn dùng Desktop, Docker hay AuraDB; nó cần đúng **URI, username, password và database name**. Có thể chuyển chúng sang biến môi trường để dùng các cấu hình khác nhau mà không sửa mã nguồn.

| Trường hợp | `NEO4J_URI` | Ghi chú |
| --- | --- | --- |
| Neo4j local trên host | `bolt://localhost:7687` | Tài khoản và DBMS cục bộ |
| Spring Boot container cùng Compose network | `bolt://neo4j:7687` | Đảm bảo hai service chung Docker network |
| AuraDB | `neo4j+s://<id>.databases.neo4j.io` | Dùng đúng URI và credential từ Aura Console |

Ví dụ `application.properties` của Spring Boot dùng Spring Data Neo4j:

~~~properties
spring.neo4j.uri=${NEO4J_URI}
spring.neo4j.authentication.username=${NEO4J_USERNAME}
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

Tạo các biến môi trường `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` ở máy chạy ứng dụng hoặc qua secret manager. Ví dụ ứng dụng chạy trên host với Docker ở mục 5 sẽ dùng `NEO4J_URI=bolt://localhost:7687` và `NEO4J_USERNAME=neo4j`; URI AuraDB sẽ theo mẫu TLS ở trên. Nếu ứng dụng cấu hình một database cụ thể, kiểm tra thêm cơ chế chọn tên database của Driver/Spring Data Neo4j tương ứng với phiên bản đang dùng.

**Không in password ra log**, không hardcode credential vào mã nguồn và không đưa credential thật vào bài commit. Kết nối từ cloud qua Internet cần xem xét chính sách network, TLS và quyền hạn của tài khoản.

## 9. Lỗi thường gặp và cách xác minh

| Triệu chứng | Nguyên nhân thường gặp | Bước kiểm tra |
| --- | --- | --- |
| Browser không mở được `localhost:7474` | DBMS/container chưa chạy, port bị chiếm, khác port cấu hình | Kiểm tra trạng thái Desktop hoặc `docker compose ps` và `docker compose logs neo4j` |
| Java Driver báo `Connection refused` | Sai host/port hoặc DBMS chưa sẵn sàng | Kiểm tra URI, tiến trình Neo4j và địa chỉ thật từ nơi ứng dụng chạy |
| Trong container kết nối `localhost:7687` thất bại | `localhost` đang là container ứng dụng | Nếu cùng Compose network, chuyển sang tên service `neo4j:7687` |
| `Authentication failed` | Sai password, nhầm instance hoặc volume giữ credential cũ | Đối chiếu username/password đúng instance; nhớ `NEO4J_AUTH` chỉ khởi tạo lần đầu |
| Container liên tục restart / out of memory | Tài nguyên Docker không đủ, cấu hình bộ nhớ quá lớn | Xem log, giới hạn tài nguyên, yêu cầu RAM/đĩa của bản Neo4j |
| AuraDB không resolve được hostname | URI sai, instance bị pause, DNS/mạng bị chặn | Xem trạng thái Aura Console trước; kiểm tra hostname và chính sách mạng |
| AuraDB lỗi TLS / certificate | Sai scheme, endpoint hoặc chính sách mạng | Dùng nguyên URI `neo4j+s://` Aura cung cấp và xác minh chuỗi chứng chỉ |
| Tắt container rồi mất dữ liệu | Không gắn volume `/data` hoặc vô tình xóa volume | Kiểm tra cấu hình volume; tránh `docker compose down -v` khi cần giữ dữ liệu |
| Chạy lại Compose nhưng mật khẩu mới không có hiệu lực | Volume đã có tài khoản ban đầu | Sử dụng cơ chế đổi mật khẩu của Neo4j; không kỳ vọng `NEO4J_AUTH` ghi đè |

Nếu dùng AuraDB, không có quyền truy cập trực tiếp ổ đĩa/tiến trình DBMS như khi tự cài. Ngược lại, với local/Docker bạn chịu trách nhiệm về cập nhật, phân quyền, lưu trữ và khôi phục. Hai mô hình cần quy trình vận hành khác nhau.

## 10. Bài tập lựa chọn môi trường

**Tình huống 1 — Học Cypher trên laptop cá nhân:** Người học muốn dựng đồ thị bạn bè, tự tạo node/relationship, đôi khi không có Internet. **Lựa chọn phù hợp:** Neo4j Desktop; Docker cũng hợp lý nếu đã quen terminal và cần tái lập môi trường.

**Tình huống 2 — Nhóm Java/Spring Boot:** Bốn thành viên cần cùng phiên bản DBMS khi chạy test tích hợp, mỗi người có dữ liệu thử nghiệm riêng. **Lựa chọn phù hợp:** Docker Compose với image cố định và volume riêng từng môi trường; đồng bộ source cấu hình nhưng giữ credential ra ngoài Git.

**Tình huống 3 — Demo ứng dụng từ nhiều địa điểm:** Nhóm muốn chạy POC mà không bật laptop 24/7 hay tự cấu hình server mạng công cộng. **Lựa chọn phù hợp:** AuraDB cho mục đích demo; chọn tier dựa trên giới hạn, tình trạng pause và độ sẵn sàng cần thiết.

**Tình huống 4 — Dịch vụ production quan trọng:** Công ty yêu cầu phân quyền, lịch backup, giám sát, khôi phục sau sự cố và mục tiêu SLA. **Lựa chọn:** đánh giá tier AuraDB có hỗ trợ yêu cầu hoặc kiến trúc Neo4j tự quản lý tương ứng; không kết luận chỉ từ việc chạy được `RETURN 1`.

### Checklist hoàn thành bài

- [ ] Giải thích được sự khác nhau giữa DBMS local, container và managed service.
- [ ] Chọn một môi trường và nêu ít nhất ba lý do phù hợp với nhu cầu.
- [ ] Biết URI của giao diện Browser và URI dành cho Driver.
- [ ] Khởi động DBMS, đăng nhập thành công, chạy `RETURN 1 AS ok`.
- [ ] Tạo và đọc lại mẫu `Student-[:ENROLLED_IN]->Course`.
- [ ] Kiểm tra dữ liệu còn tồn tại sau khi kết nối lại / khởi động lại.
- [ ] Biết nơi lưu credential, nơi lưu dữ liệu và cách không xóa nhầm volume.

## 11. Tài liệu tham khảo chính thức

- [Neo4j Desktop](https://neo4j.com/docs/desktop/current/) — tạo và quản lý DBMS cục bộ.
- [Neo4j Operations Manual: Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/) — khởi tạo container, xác thực và lưu dữ liệu.
- [Neo4j Operations Manual: Docker Compose](https://neo4j.com/docs/operations-manual/current/docker/docker-compose-standalone/) — cấu hình Compose và quản lý credential.
- [Neo4j Aura: Create an instance](https://neo4j.com/docs/aura/getting-started/create-instance/) — tạo instance cloud.
- [Neo4j Aura: Connect to an instance](https://neo4j.com/docs/aura/getting-started/connect-instance/) — lấy URI và kết nối ứng dụng.
- [Neo4j Aura: Pricing](https://neo4j.com/pricing/) — đối chiếu khả năng của Free và các tier trả phí tại thời điểm triển khai.

> **Ghi chú phiên bản:** Tag Docker trong ví dụ là một phiên bản được tài liệu Neo4j dùng ở thời điểm biên soạn; khi thực hành về sau cần kiểm tra vòng đời hỗ trợ và hướng dẫn nâng cấp trên trang chính thức.
