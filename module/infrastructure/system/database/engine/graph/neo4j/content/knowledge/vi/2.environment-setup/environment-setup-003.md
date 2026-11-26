# Khởi chạy bằng Docker Compose với dữ liệu lưu bền và cấu hình riêng

## 1. Mục tiêu và kết quả cần đạt

Trong Neo4j, dữ liệu được lưu dưới dạng **property graph**: **node** mô tả thực thể, **relationship** biểu diễn quan hệ có hướng, và **property** lưu thuộc tính của node/relationship. Để thực hành **Cypher**, index, constraint, truy vấn đường đi, nhập dữ liệu hoặc kết nối qua **Java Driver** và **Spring Data Neo4j**, người học cần một Neo4j DBMS chạy ổn định, có cấu hình tái tạo được và **không mất dữ liệu khi tạo lại container**.

**Docker Compose** cho phép mô tả image Neo4j, cổng mạng, biến môi trường, volume và secret trong các tệp cấu hình. Cùng một định nghĩa Compose có thể dùng lại giữa các máy phát triển hoặc trong quy trình test tích hợp.

Sau bài học, bạn sẽ:

1. Viết `compose.yaml` chạy Neo4j bằng **image có phiên bản cố định**, không phụ thuộc tag `latest`.
2. Sử dụng **named volume** cho `/data` và `/logs` để dữ liệu tồn tại sau khi container được thay thế.
3. Tách thông số theo môi trường ra `.env` hoặc `--env-file`; dùng **Docker Compose secret** cho credential khởi tạo.
4. Kiểm tra trạng thái, đăng nhập, chạy Cypher, đọc dữ liệu sau `docker compose down` và `docker compose up -d`.
5. Phân biệt cấu hình ở host, trong container và trong ứng dụng Java/Spring Boot; xử lý lỗi thường gặp một cách có hệ thống.

> **Phạm vi:** Đây là cấu hình **một Neo4j Community Edition instance cho học tập/phát triển cục bộ**. Ví dụ sử dụng image chính thức `neo4j:2026.10.2`. Khi triển khai production, cần thiết kế riêng TLS, giám sát, backup/restore, chính sách secret, nâng cấp, tài nguyên và độ sẵn sàng cao.

## 2. Mô hình hoạt động: service, container, volume và cấu hình

Compose không tự tạo database; nó yêu cầu Docker chạy một **service** tên `neo4j` từ image đã chọn. Neo4j tạo database trong thư mục nội bộ `/data` khi DBMS khởi động lần đầu. **Volume** nối thư mục này tới vùng lưu trữ nằm ngoài writable layer của container, nên việc thay thế container không xóa graph.

~~~mermaid
flowchart LR
    U["Neo4j Browser / Java Driver trên host"] -->|"HTTP :7474 / Bolt :7687"| C["Service neo4j<br/>Container từ image pin version"]
    C -->|"ghi DB"| D[("Named volume neo4j_data<br/>mount /data")]
    C -->|"ghi log"| L[("Named volume neo4j_logs<br/>mount /logs")]
    E[".env / --env-file<br/>phiên bản, cổng, bộ nhớ"] --> C
    S["Compose secret<br/>credential khởi tạo"] --> C
~~~

### 2.1. Các lớp cấu hình khác nhau

| Thành phần | Ý nghĩa | Đọc bởi ai? | Có được commit Git không? |
| --- | --- | --- | --- |
| `compose.yaml` | Mô tả service, image, ports, volumes và secrets | Docker Compose | Có, sau khi loại bỏ bí mật |
| `.env` hoặc `.env.dev` | Giá trị nội suy vào Compose: image tag, host port, memory, đường dẫn secret | **Compose CLI** | Thông thường không; phát hành `.env.example` |
| `environment` trong Compose | Biến được truyền vào container; Neo4j đọc biến `NEO4J_*` | Container/Neo4j | Có nếu không chứa bí mật |
| `secrets/neo4j_auth.txt` | Chuỗi khởi tạo `neo4j/<password>` | Docker secret → Neo4j | **Không** |
| `neo4j_data` | Database, metadata và dữ liệu quan trọng | Neo4j trong container | Không thuộc source Git |
| `neo4j_logs` | Log ứng dụng hỗ trợ chẩn đoán | Neo4j trong container | Không thuộc source Git |

**Dễ nhầm:** đặt `NEO4J_PASSWORD=...` trong `.env` chỉ làm Compose có thể nội suy biến đó. Biến trong `.env` **không tự động đi vào container** trừ khi được tham chiếu trong `environment`, `env_file` hoặc một thuộc tính Compose thích hợp. Trong bài này, mật khẩu được cung cấp qua **secret file**, không đi qua `.env`.

### 2.2. Named volume và bind mount khác nhau thế nào?

| Loại | Ví dụ trong Compose | Ưu điểm | Cần chú ý |
| --- | --- | --- | --- |
| **Named volume** | `neo4j_data:/data` | Docker quản lý vị trí và vòng đời; ít vướng quyền đường dẫn host | Tên volume thực tế thường có **tiền tố project Compose** |
| **Bind mount** | `./data:/data` | Nhìn thấy file ngay trong thư mục host, tiện thao tác với công cụ ngoài | Dễ gặp lỗi permission, đường dẫn/OS, xóa nhầm thư mục |
| Không mount | Không có mapping cho `/data` | Dùng rất nhanh để thử image | **Mất dữ liệu khi container bị xóa/thay thế** |

> Dừng container và khởi động lại cùng container không tự xóa writable layer. Rủi ro chính của cấu hình **không mount** là khi container bị **remove/recreate**. Vì thế cần gắn `/data` vào volume ngay từ đầu.

## 3. Điều kiện tiên quyết

Bạn cần máy Windows, macOS hoặc Linux chạy được **Docker Engine/Docker Desktop** và **Docker Compose v2**. Đối với ví dụ giới hạn bộ nhớ ở mức lab, hãy dành đủ RAM cho hệ điều hành, Docker và Neo4j; máy có khoảng **4 GB RAM khả dụng cho Docker trở lên** thuận tiện hơn khi thực hành. Dung lượng ổ đĩa phải đủ cho image, graph, log và dữ liệu phát sinh. Không xem các mức này là sizing production.

Kiểm tra môi trường:

~~~bash
docker --version
docker compose version
docker info
~~~

- `docker --version` cho biết Docker CLI được cài.
- `docker compose version` xác nhận Compose plugin v2.
- `docker info` cho biết CLI có truy cập được Docker daemon/Engine.

Nếu `docker info` lỗi vì không kết nối daemon, khởi động Docker Desktop hoặc dịch vụ Docker rồi kiểm tra lại. Nếu máy có Neo4j cục bộ khác, kiểm tra cổng `7474` (HTTP) và `7687` (Bolt) trước khi chạy thêm instance.

**Không cần cài Java cho host chỉ để chạy Neo4j bằng Docker:** image Neo4j đã mang runtime phù hợp cho server. Nếu đồng thời viết ứng dụng Spring Boot trên host thì ứng dụng đó cần JDK và Java Driver tương thích riêng.

## 4. Chuẩn bị cấu trúc thư mục dự án

Tạo một thư mục riêng, chẳng hạn `neo4j-compose-lab`:

~~~text
neo4j-compose-lab/
├── compose.yaml
├── .env
├── .env.example
├── .gitignore
└── secrets/
    └── neo4j_auth.txt
~~~

Tất cả ví dụ `docker compose` bên dưới được chạy tại **thư mục chứa `compose.yaml`**. Trong bài viết, đây là các file **người học tự tạo trong lab**, không phải file mới cần thêm vào source của module tài liệu.

### 4.1. File `compose.yaml` — cấu hình service

~~~yaml
services:
  neo4j:
    image: "${NEO4J_IMAGE:-neo4j:2026.10.2}"

    ports:
      - "127.0.0.1:${NEO4J_HTTP_PORT:-7474}:7474"
      - "127.0.0.1:${NEO4J_BOLT_PORT:-7687}:7687"

    environment:
      NEO4J_AUTH_FILE: /run/secrets/neo4j_auth
      NEO4J_server_memory_heap_initial__size: "${NEO4J_HEAP:-512m}"
      NEO4J_server_memory_heap_max__size: "${NEO4J_HEAP:-512m}"
      NEO4J_server_memory_pagecache_size: "${NEO4J_PAGECACHE:-512m}"

    secrets:
      - neo4j_auth

    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

    restart: unless-stopped
    stop_grace_period: 2m

secrets:
  neo4j_auth:
    file: "${NEO4J_AUTH_SOURCE:-./secrets/neo4j_auth.txt}"

volumes:
  neo4j_data:
  neo4j_logs:
~~~

**Giải thích những lựa chọn quan trọng:**

- `image` lấy từ biến `NEO4J_IMAGE`, mặc định `neo4j:2026.10.2` — tag Community Edition đã được Neo4j công bố. Pin phiên bản để kết quả thực hành lặp lại được giữa các máy; khi nâng cấp phải thực hiện quy trình kiểm tra tương thích dữ liệu.
- `127.0.0.1:7474:7474` và `127.0.0.1:7687:7687` chỉ publish HTTP và Bolt lên **loopback của host**. Truy cập từ máy khác cần thiết kế mạng và TLS riêng, không tùy tiện đổi sang `0.0.0.0`.
- `NEO4J_AUTH_FILE` trỏ tới **file được Compose secret mount** trong container, không trỏ vào đường dẫn trên host.
- Ba biến `NEO4J_server_memory_*` dùng cú pháp chuyển đổi thiết lập Neo4j thành environment variable: **dấu chấm `.` → `_`, dấu gạch dưới `_` → `__`**. Ví dụ `server.memory.heap.max_size` trở thành `NEO4J_server_memory_heap_max__size`.
- `neo4j_data:/data` giữ database sau khi thay thế container; `neo4j_logs:/logs` giữ log để phân tích lỗi.
- `stop_grace_period: 2m` cho Neo4j thêm thời gian dừng có kiểm soát trước khi Docker có thể buộc kết thúc. Cần điều chỉnh theo workload thực tế.
- `restart: unless-stopped` hỗ trợ Docker khởi động lại container nếu dịch vụ/daemon được khởi động lại, trừ trường hợp dừng chủ động.

Đây là cấu hình cho **một instance phát triển**, không áp đặt TLS, backup hay resource isolation kiểu production.

### 4.2. File `.env` — cấu hình riêng cho máy của bạn

~~~dotenv
NEO4J_IMAGE=neo4j:2026.10.2
NEO4J_HTTP_PORT=7474
NEO4J_BOLT_PORT=7687
NEO4J_HEAP=512m
NEO4J_PAGECACHE=512m
NEO4J_AUTH_SOURCE=./secrets/neo4j_auth.txt
~~~

Bạn có thể chia sẻ **`.env.example`** với các **giá trị mẫu không chứa bí mật** để đồng đội biết tên biến phải điền. Mỗi người tạo `.env` riêng. Với máy có nhiều instance, đổi host port ở `NEO4J_HTTP_PORT` và `NEO4J_BOLT_PORT`; **cổng trong container vẫn là 7474/7687** trừ khi thay cấu hình lắng nghe của Neo4j.

Chẳng hạn, đặt `NEO4J_HTTP_PORT=7475` và `NEO4J_BOLT_PORT=7688` thì URL trên **host** là `http://localhost:7475` và `bolt://localhost:7688`. Bên trong mạng Compose, ứng dụng khác vẫn gọi service Neo4j tại `neo4j:7687`.

### 4.3. Tạo secret xác thực — không commit mật khẩu

Tạo file `secrets/neo4j_auth.txt` (văn bản UTF-8) với nội dung **một dòng**:

~~~text
neo4j/REPLACE_WITH_YOUR_OWN_LONG_RANDOM_PASSWORD
~~~

Thay placeholder bằng mật khẩu mạnh, duy nhất; không sử dụng chuỗi mẫu để chạy thật. File này chỉ được Neo4j dùng khi **khởi tạo authentication của database chưa có sẵn**. Thay nội dung file sau khi database đã khởi tạo **không tự đổi mật khẩu của tài khoản đang tồn tại**.

Trong `.gitignore`:

~~~gitignore
.env
.env.*
!.env.example
secrets/
~~~

Khi cần dùng file cấu hình riêng có chứa bí mật, cũng phải đưa file đó vào danh sách loại trừ phù hợp. **Compose secret trên máy phát triển là file trên host được mount vào container**; đừng coi nó tự động được mã hóa hoặc bảo vệ như một secret manager. Bảo vệ quyền truy cập thư mục và sử dụng cơ chế secret của hạ tầng khi triển khai thực tế.

### 4.4. Kiểm tra Compose trước khi khởi chạy

~~~bash
docker compose config --quiet
docker compose config --images
~~~

`config --quiet` kiểm tra cú pháp và nội suy cấu hình; `config --images` cho biết image thực tế Compose sẽ dùng. Nếu biến `NEO4J_AUTH_SOURCE` trỏ sai hoặc file secret chưa tồn tại, hãy chỉnh đúng đường dẫn và tạo file trước khi chạy. **Không** đưa output của cấu hình có credential nhạy cảm vào ticket/chat.

## 5. Khởi động Neo4j và xác nhận DBMS sẵn sàng

Trong thư mục project:

~~~bash
docker compose pull neo4j
docker compose up -d
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Giải thích:

1. `pull` tải image theo tag đã pin; lần đầu có thể cần Internet.
2. `up -d` tạo volume, secret mount, network và container, rồi chạy service ở chế độ nền.
3. `ps` cho biết service có ở trạng thái `running` không; **running chưa đồng nghĩa server đã nhận truy vấn**.
4. `logs` giúp kiểm tra lỗi xác thực ban đầu, quyền đọc secret, bộ nhớ, port hoặc quá trình Neo4j startup.

Đợi log cho biết Neo4j đã sẵn sàng, sau đó mở **http://localhost:7474** và đăng nhập bằng:

- **Username:** `neo4j`.
- **Password:** phần sau dấu `/` trong `secrets/neo4j_auth.txt`.
- **Database:** thường là `neo4j` đối với lab mới; xác nhận giá trị thật trong DBMS.

Neo4j Browser dùng giao diện HTTP; ứng dụng Java/Spring Data Neo4j dùng **Bolt** qua `bolt://localhost:7687` (khi chạy trên host). Không dùng HTTP URL để khởi tạo Neo4j Java Driver.

### 5.1. Xác minh bằng Cypher

Chạy trong Browser:

~~~cypher
RETURN 1 AS ok, datetime() AS serverTime;
~~~

Kết quả mong đợi: một dòng có `ok = 1`. Tiếp theo, kiểm tra đúng version/edition:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

`versions` cần chứa phiên bản DBMS thực tế, ví dụ `2026.10.2`, và `edition` cho biết Community/Enterprise. Việc tên image đúng chưa đủ để kết luận instance kết nối là đúng DBMS nếu trên máy đang có nhiều container hay nhiều cổng publish.

Nếu dùng terminal có hỗ trợ tương tác, có thể mở Cypher Shell trong container:

~~~bash
docker compose exec neo4j cypher-shell -u neo4j -d neo4j
~~~

Cypher Shell sẽ yêu cầu mật khẩu nếu không được cung cấp qua flag. Cách này tránh đưa plaintext password vào lịch sử lệnh; nếu môi trường shell không tương tác thì ưu tiên dùng Browser hoặc một cơ chế truyền credential an toàn phù hợp.

## 6. Bài thử quan trọng: dữ liệu vẫn còn sau khi tạo lại container

### 6.1. Tạo một property graph nhỏ

Ví dụ mô hình người học đăng ký khóa học:

~~~cypher
MERGE (s:Student {studentId: 'docker-lab-001'})
  ON CREATE SET s.name = 'An'
MERGE (c:Course {courseId: 'neo4j-compose'})
  ON CREATE SET c.title = 'Neo4j voi Docker Compose'
MERGE (s)-[:ENROLLED_IN]->(c)
RETURN s.name AS student, c.title AS course;
~~~

Đọc quan hệ và đường đi:

~~~cypher
MATCH p = (:Student {studentId: 'docker-lab-001'})
          -[:ENROLLED_IN]->
          (:Course {courseId: 'neo4j-compose'})
RETURN p;
~~~

Neo4j sẽ trả một đường đi chứa node `Student`, node `Course` và relationship `ENROLLED_IN`. `MERGE` phù hợp cho bài lab chạy lại nhiều lần; với dữ liệu nhiều luồng và production, vẫn cần **uniqueness constraint** cho khóa nghiệp vụ và cân nhắc transaction.

### 6.2. Dừng, xóa container rồi khởi chạy lại

Thực hiện tại **chính thư mục/project Compose** đã dùng trước đó:

~~~bash
# Dung va xoa container/network Compose, NHUNG giu named volumes
docker compose down

# Khoi tao container moi tu cung image va volume
docker compose up -d
docker compose ps
~~~

Đợi Neo4j khởi động xong, đăng nhập lại và chạy truy vấn `MATCH p = ... RETURN p` ở mục 6.1. Nếu đường đi cũ vẫn còn, dữ liệu đã được giữ qua vòng đời container bởi named volume.

**Tại sao lại tồn tại?** Compose quản lý volume được khai báo ở root `volumes`. Khi `down` không có cờ `-v`, Docker giữ volume và gắn lại vào `/data` khi chạy `up`. Dữ liệu, account và metadata nằm trong volume được tái sử dụng.

**Lệnh cần phân biệt rõ:**

| Lệnh | Container và network | Named volume chứa database |
| --- | --- | --- |
| `docker compose stop` | Dừng, vẫn giữ container | Giữ nguyên |
| `docker compose start` | Khởi chạy container đã dừng | Giữ nguyên |
| `docker compose down` | Xóa container/network Compose | **Giữ nguyên** theo mặc định |
| `docker compose up -d --force-recreate` | Tạo lại container | **Giữ nguyên** nếu giữ cấu hình volume/project |
| `docker compose down -v` | Xóa container/network **và các volume do Compose quản lý** | **Xóa dữ liệu của volume trong ví dụ** |
| `docker volume prune` | Không phải thao tác chuyên biệt cho project này | Có thể xóa volume không còn được tham chiếu; không dùng khi còn dữ liệu cần giữ |

> **Cảnh báo quan trọng:** `docker compose down -v` hoặc xóa named volume là **hành động mất dữ liệu**. Đừng chạy để “thử cho sạch” trên database có giá trị. Chỉ thực hiện khi chủ đích hủy môi trường và đã xác minh bản sao lưu.

### 6.3. Xác định tên volume thật

~~~bash
docker compose ls
docker volume ls
docker compose ps
~~~

Compose thường đặt tên volume thực theo mẫu **`<project>_neo4j_data`**, trong đó `project` mặc định xuất phát từ tên thư mục hoặc biến `COMPOSE_PROJECT_NAME` / tham số `-p`. Nếu thay tên project, Compose có thể tạo **volume khác**, dẫn đến cảm giác “database biến mất” dù volume cũ vẫn còn.

Vì vậy, **đừng đổi tùy tiện project name** giữa `down` và `up`. Nếu muốn giữ tên volume độc lập project, có thể khai báo `name:` dưới volume, nhưng khi đó phải quản lý tránh việc nhiều dự án cùng dùng chung database. Trong lab, giữ nguyên project name là đủ.

## 7. Dùng cấu hình riêng cho từng môi trường

Để không trộn dữ liệu, cổng và credential giữa **dev** và **test**, có thể tạo hai file giá trị và hai secret tương ứng. Không cần nhân bản toàn bộ `compose.yaml`.

### 7.1. Hai file môi trường

File `.env.dev`:

~~~dotenv
NEO4J_IMAGE=neo4j:2026.10.2
NEO4J_HTTP_PORT=7474
NEO4J_BOLT_PORT=7687
NEO4J_HEAP=512m
NEO4J_PAGECACHE=512m
NEO4J_AUTH_SOURCE=./secrets/dev_auth.txt
~~~

File `.env.test`:

~~~dotenv
NEO4J_IMAGE=neo4j:2026.10.2
NEO4J_HTTP_PORT=7475
NEO4J_BOLT_PORT=7688
NEO4J_HEAP=512m
NEO4J_PAGECACHE=512m
NEO4J_AUTH_SOURCE=./secrets/test_auth.txt
~~~

Tạo riêng hai secret với mật khẩu khác nhau theo định dạng `neo4j/<password>`. Các file giá trị nên được loại khỏi Git và chia sẻ mẫu `.env.example`.

### 7.2. Chạy với `--env-file` và project name khác nhau

~~~bash
# Dung cho moi truong dev
docker compose --env-file .env.dev -p neo4j-dev up -d

# Dung cho moi truong test
docker compose --env-file .env.test -p neo4j-test up -d
~~~

Kết quả:

- **Dev:** `http://localhost:7474`, `bolt://localhost:7687` và volume có tiền tố `neo4j-dev`.
- **Test:** `http://localhost:7475`, `bolt://localhost:7688` và volume có tiền tố `neo4j-test`.
- Hai service Neo4j có thể cùng chạy nếu tài nguyên máy và port cho phép; không chia sẻ data volume.

Khi đọc log/dừng, **dùng đúng tham số môi trường và project**:

~~~bash
docker compose --env-file .env.dev -p neo4j-dev logs --tail=80 neo4j
docker compose --env-file .env.test -p neo4j-test ps
docker compose --env-file .env.test -p neo4j-test down
~~~

Nếu chạy `docker compose down` mà bỏ `-p`, Compose có thể thao tác với **project khác**, nên không dừng được instance dự định. Thiết lập nhất quán lệnh và project name trong tài liệu nhóm.

### 7.3. Cấu hình Neo4j riêng qua biến môi trường

Neo4j Docker chuyển các biến bắt đầu bằng `NEO4J_` thành thiết lập trong `neo4j.conf` theo quy tắc ở mục 4.1. Ví dụ thêm vào `environment`:

~~~yaml
NEO4J_server_memory_heap_initial__size: "512m"
NEO4J_server_memory_heap_max__size: "512m"
NEO4J_server_memory_pagecache_size: "512m"
~~~

Các biến này tương ứng `server.memory.heap.initial_size`, `server.memory.heap.max_size` và `server.memory.pagecache.size`. Chọn giá trị theo tài nguyên thực, tránh đặt tổng heap + page cache gần sát giới hạn RAM vì JVM và các tiến trình còn cần bộ nhớ ngoài heap.

Nếu muốn đặt thêm cấu hình Cypher, logs hay database path, **tra đúng tên setting được hỗ trợ bởi phiên bản Neo4j**. Một tên setting từ Neo4j 4.x có thể đã đổi trong Neo4j 5.x/2026.x; tránh mang nguyên cấu hình đời cũ vào image mới.

### 7.4. Khi nào cần file `neo4j.conf` riêng?

Với tùy chỉnh nhiều setting, có thể **bind mount** thư mục `./conf` vào `/conf` trong container, nhưng **đây không phải thao tác thêm vài dòng lên cấu hình gốc một cách tự động**. File trong `/conf` sẽ **thay thế cấu hình được cung cấp bởi image**; phải bảo đảm bộ file cấu hình đầy đủ và đúng phiên bản. Nếu mount một thư mục rỗng, DBMS có thể khởi động sai hoặc không khởi động. Biến môi trường `NEO4J_*` có độ ưu tiên cao hơn giá trị trong file `/conf`.

Theo tài liệu Neo4j, có thể chạy image với lệnh `dump-config` để lấy bộ cấu hình ban đầu ra thư mục mount, rồi mới điều chỉnh. Khi mount `/conf` cần bảo đảm `server.default_listen_address=0.0.0.0` để connector lắng nghe trên các interface bên trong container, phù hợp với cách publish port của Docker.

Với ví dụ lab này, **ưu tiên cấu hình qua environment variables** để giảm rủi ro do sai file cấu hình. Chỉ chọn `/conf` khi thực sự cần cấu hình dài và đã kiểm tra độ tương thích.

## 8. Kết nối từ ứng dụng Java và Spring Data Neo4j

Khi service Neo4j chạy trong container, địa chỉ kết nối phụ thuộc **nơi ứng dụng đang chạy**:

| Ứng dụng | Bolt URI | Lý do |
| --- | --- | --- |
| Java/Spring Boot chạy trên **host** | `bolt://localhost:7687` (dev) hoặc `bolt://localhost:7688` (test) | Dùng **host port** đã publish |
| Java/Spring Boot trong **cùng Compose network** với service Neo4j | `bolt://neo4j:7687` | Docker DNS phân giải tên service `neo4j`, dùng **container port** |
| Máy khác trong mạng | Không dùng cấu hình loopback của lab | Cần thiết kế kết nối riêng, xác thực và TLS |

Nếu Spring Boot chạy trong container khác, `localhost` chỉ container **Spring Boot**, không phải Neo4j. Đừng đổi host port và kỳ vọng URI `neo4j:7687` của container ứng dụng cũng đổi.

Ví dụ `application.properties`:

~~~properties
spring.neo4j.uri=${NEO4J_URI}
spring.neo4j.authentication.username=${NEO4J_USERNAME}
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

Biến môi trường của ứng dụng Java phải được cấp qua công cụ chạy ứng dụng hoặc cấu hình riêng. Secret `neo4j_auth` của service Neo4j **không tự động được chia sẻ sang container Java**; nếu dùng secret chung cần thiết kế rõ quyền và cách ứng dụng đọc secret.

**Phân biệt khởi động và sẵn sàng:** `depends_on` cơ bản chỉ ràng buộc thứ tự tạo/chạy container. Ứng dụng Java có thể mở kết nối khi DBMS chưa sẵn sàng nhận truy vấn; cần cơ chế kết nối lại có giới hạn, hoặc healthcheck phù hợp nếu quy trình triển khai cần đảm bảo readiness. Không nên coi `docker compose ps` báo “running” là đủ thay cho bài kiểm tra Cypher.

## 9. Dữ liệu bền vững không thay thế sao lưu

Named volume giải quyết **lưu giữ dữ liệu khi container được thay thế**; nó không bảo vệ khỏi lỗi phần cứng, xóa volume, hỏng store, query xóa nhầm hoặc nâng cấp thất bại.

- **Lưu bền (persistence):** giữ database ở `/data` bên ngoài writable layer của container.
- **Backup:** tạo bản sao nhất quán có thể dùng để khôi phục ở nơi khác, theo công cụ và khả năng của phiên bản/edition.
- **Restore:** quy trình đưa database về trạng thái từ bản backup đã kiểm tra.
- **Upgrade/migration:** đánh giá tính tương thích của DBMS, plugin, dữ liệu và Cypher trước khi thay image.

Đối với lab nhỏ, có thể dùng các cơ chế **neo4j-admin database dump/load** theo hướng dẫn phù hợp edition và trạng thái database, hoặc xuất dữ liệu mô hình thành CSV/Cypher để dễ tạo lại. Không sao chép thô các file đang được database ghi mà mặc định cho rằng bản sao đó nhất quán. Với hệ thống quan trọng cần dùng quy trình backup online/offline được Neo4j hỗ trợ cho edition đó và **kiểm thử restore**.

Khi đổi `NEO4J_IMAGE` từ `2026.10.2` sang một bản mới hơn, **không chỉ đổi tag rồi `up -d` trên dữ liệu quan trọng**: phải xem release notes, upgrade/migration guide và khả năng quay lui/khôi phục. Volume tồn tại không đồng nghĩa data store tương thích ngược với bản cũ.

## 10. Khắc phục sự cố thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| `docker compose config` báo lỗi biến/secret | Sai cú pháp YAML, thiếu file `.env` hoặc file secret | Kiểm tra đường dẫn tương đối theo project, cú pháp nội suy và dòng `secrets:` |
| `Cannot connect to Docker daemon` | Docker Engine/Desktop chưa chạy | Kiểm tra `docker info`, khởi động Docker |
| Port `7474` hoặc `7687` đã được dùng | Instance Neo4j khác hoặc chương trình khác chiếm port host | Kiểm tra port, đổi giá trị host port trong `.env` |
| Container `running` nhưng Browser lỗi | Neo4j đang startup, lỗi cấu hình hoặc sai host port | `docker compose logs --tail=100 neo4j` và kiểm tra `ps` |
| `Authentication failed` | Sai secret, đang vào instance khác, hoặc volume giữ mật khẩu cũ | Đối chiếu host port/project, secret lần đầu, dùng quy trình đổi mật khẩu của Neo4j |
| Chỉnh `NEO4J_AUTH_SOURCE` nhưng mật khẩu không đổi | Secret chỉ khởi tạo auth khi database chưa tồn tại | Không xóa volume để reset tùy tiện; đổi mật khẩu qua lệnh quản trị phù hợp |
| Tạo lại container mà graph trống | Khác Compose project name/volume hoặc trước đó không mount `/data` | Kiểm tra `docker volume ls` và lệnh `-p`; tìm volume cũ trước khi sửa |
| `Permission denied` trên `/data` | Bind mount host không cho UID/GID container ghi | Kiểm tra owner/permissions theo tài liệu Neo4j; với lab dùng named volume |
| JVM bị kill/OOM | RAM cấp Docker quá ít, heap/page cache quá lớn | Xem log và RAM host/engine; điều chỉnh biến memory phù hợp |
| `Connection refused` từ ứng dụng container | URI đang dùng `localhost:7687` | Nếu cùng Compose network, dùng `bolt://neo4j:7687` |
| Gắn `./conf:/conf` xong Neo4j không khởi động | Thư mục `conf` rỗng/thiếu cấu hình quan trọng hoặc sai setting | Khôi phục bộ config đúng phiên bản, xem log; dùng environment variables cho thay đổi nhỏ |
| Data tồn tại nhưng query khác sau nâng phiên bản | Ngôn ngữ Cypher hoặc tính năng DBMS thay đổi | Kiểm tra `dbms.components()`, cấu hình Cypher, release/upgrade notes |

Quy trình kiểm tra nên đi từ **Compose config → Docker daemon → container/log → port → credential → database → Cypher**. Không xóa volume khi chưa xác định nguyên nhân.

## 11. Bài tập thực hành

### Bài tập 1 — Chứng minh data persistence

1. Chạy `docker compose up -d` với `neo4j_data:/data`.
2. Tạo node/relationship bằng Cypher ở mục 6.1 và chụp lại kết quả `MATCH`.
3. Chạy `docker compose down`, rồi `docker compose up -d`.
4. Chạy lại `MATCH`, giải thích vì sao dữ liệu vẫn tồn tại và chỉ ra nơi nó được lưu.

**Kết quả đạt:** node `Student`, node `Course` và relationship `ENROLLED_IN` còn nguyên.

### Bài tập 2 — Hai môi trường độc lập

Tạo `.env.dev` và `.env.test` với host port khác nhau; chạy lần lượt `-p neo4j-dev` và `-p neo4j-test`. Tạo node có cùng `studentId` nhưng `name` khác nhau trong mỗi instance. Kết nối lại từng host port và chứng minh dữ liệu không bị trộn. Sau đó dừng **chỉ test** mà vẫn giữ dev chạy.

**Kết quả đạt:** hai volume có project prefix khác nhau; việc `down` test không làm ngắt dev.

### Bài tập 3 — Chẩn đoán lỗi kết nối Java

Ứng dụng Spring Boot chạy bằng một service khác trong cùng Compose network, nhưng dùng `bolt://localhost:7687` và bị từ chối kết nối. Giải thích `localhost` đang trỏ tới đâu, thay URI thành `bolt://neo4j:7687`, và nêu cách kiểm tra khi DBMS chưa sẵn sàng.

### Bài tập 4 — Mật khẩu không đổi sau khởi tạo

Một thành viên sửa `secrets/neo4j_auth.txt` rồi chạy `docker compose down` và `up -d`, nhưng đăng nhập bằng mật khẩu mới thất bại. Hãy giải thích vai trò **khởi tạo một lần** của `NEO4J_AUTH_FILE` và đề xuất đổi mật khẩu bằng công cụ quản trị Neo4j. Không đề xuất xóa volume nếu database cần giữ.

### Checklist nghiệm thu môi trường

- [ ] `docker compose config --quiet` thành công, image tag rõ ràng.
- [ ] Compose chạy được; Browser `localhost:7474` và Bolt host `localhost:7687` kết nối đúng.
- [ ] `CALL dbms.components()` trả đúng Neo4j version/edition.
- [ ] Đã tạo và đọc graph có node, relationship, property.
- [ ] Dữ liệu còn sau `down` rồi `up -d` với cùng project name.
- [ ] Biết nơi đặt named volume, log và secret.
- [ ] Không đưa file secret, mật khẩu hay data volume vào Git.
- [ ] Phân biệt URI host với URI nội bộ Docker service.
- [ ] Hiểu `down -v` có thể làm mất dữ liệu và volume không phải backup.

## 12. Tài liệu tham khảo chính thức

- [Neo4j Operations Manual — Deploy a standalone server using Docker Compose](https://neo4j.com/docs/operations-manual/current/docker/docker-compose-standalone/) — ví dụ Compose, authentication và Docker secrets.
- [Neo4j Operations Manual — Persisting data with Docker volumes](https://neo4j.com/docs/operations-manual/current/docker/mounting-volumes/) — mount points `/data`, `/logs`, `/conf` và quyền file.
- [Neo4j Operations Manual — Docker-specific configuration settings](https://neo4j.com/docs/operations-manual/current/docker/ref-settings/) — quy tắc đổi `neo4j.conf` thành biến `NEO4J_*`.
- [Neo4j Operations Manual — Modify the default configuration](https://neo4j.com/docs/operations-manual/current/docker/configuration/) — `/conf`, `dump-config` và thứ tự ưu tiên cấu hình.
- [Neo4j Operations Manual — Getting started with Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/) — image, edition, phiên bản và kết nối.
- [Docker Compose — Environment variables and interpolation](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/) — `.env`, `--env-file` và biến Compose.
- [Docker Compose — Secrets](https://docs.docker.com/compose/how-tos/use-secrets/) — quyền truy cập secret qua file được mount.
- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/) — đánh giá thay đổi phiên bản trước khi tái sử dụng data volume.

**Kết luận thực hành:** Một Docker Compose Neo4j tốt cho phát triển cần **phiên bản image cố định**, **`/data` mount ra named volume**, **cấu hình theo môi trường**, **credential không nằm trong mã nguồn** và **quy trình Cypher kiểm chứng sau khi tạo lại container**. Đây là nền tảng để tiếp tục học Cypher, thiết kế graph và tích hợp Java một cách tái tạo được.
