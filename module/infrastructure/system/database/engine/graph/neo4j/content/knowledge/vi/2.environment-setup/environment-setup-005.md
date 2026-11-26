# Tạo tài khoản ban đầu, đổi mật khẩu và kiểm tra kết nối

## 1. Mục tiêu và bối cảnh

Neo4j là hệ quản trị cơ sở dữ liệu đồ thị sử dụng mô hình **property graph**. Dữ liệu gồm **node**, **relationship** có hướng và **property**; ngôn ngữ **Cypher** giúp tìm mẫu quan hệ, truy vấn đường đi và cập nhật dữ liệu. Trước khi học sâu về index, constraint, tối ưu truy vấn, nhập dữ liệu hay tích hợp Java Driver và Spring Data Neo4j, ta phải truy cập được **đúng Neo4j DBMS** với **tài khoản hợp lệ**.

Bài này thuộc chương **Khởi tạo môi trường**, tập trung vào vòng đời thông tin đăng nhập: **thiết lập tài khoản ban đầu → đăng nhập lần đầu → đổi mật khẩu → xác minh kết nối và truy vấn → bảo quản credential**.

Sau bài học, bạn có thể:

1. Phân biệt tài khoản mặc định `neo4j`, mật khẩu khởi tạo và mật khẩu đã được thay đổi.
2. Tạo credential ban đầu cho Neo4j Desktop, server tự cài, Docker Compose và Neo4j AuraDB.
3. Đổi mật khẩu đang biết bằng giao diện hoặc Cypher `ALTER CURRENT USER SET PASSWORD`.
4. Xác minh danh tính và quyền truy cập bằng Neo4j Browser, Cypher Shell và Java Driver.
5. Chẩn đoán các lỗi xác thực, URI, cổng, TLS hoặc tên database mà không làm mất dữ liệu.

> **Phạm vi:** Ví dụ dùng tài khoản xác thực nội bộ (**native authentication**) của một Neo4j DBMS độc lập, chủ yếu để học tập. Cơ chế nhiều người dùng, vai trò/quyền, SSO/OIDC, LDAP và quy trình khôi phục quản trị khác nhau theo **edition**, phiên bản và môi trường. Tài liệu mô tả Neo4j hiện hành, minh họa bằng image `neo4j:2026.10.2`; hãy đối chiếu hướng dẫn của đúng phiên bản bạn sử dụng.

## 2. Hiểu tài khoản Neo4j và các trạng thái mật khẩu

### 2.1. Xác thực khác phân quyền

- **Authentication (xác thực)** trả lời: *ai đang kết nối?* Ví dụ tên người dùng `neo4j` và mật khẩu do bạn đã đặt.
- **Authorization (phân quyền)** trả lời: *người đó được làm gì?* Ví dụ quyền đọc dữ liệu, ghi node/relationship, tạo index/constraint hoặc quản lý user.
- **Database** là nơi thực thi truy vấn đồ thị. Một DBMS có thể quản lý một hoặc nhiều database tùy edition và cấu hình; mật khẩu thuộc **user của DBMS**, không được thiết lập riêng bằng cách gõ một lệnh vào mỗi node.

Trong cài đặt local thông thường với native authentication, **tên tài khoản quản trị ban đầu là `neo4j`**. Tên đăng nhập này **khác** tên database `neo4j`, dù trong nhiều lab cả hai cùng mang chuỗi `neo4j`.

| Khái niệm | Ví dụ minh họa | Chú ý |
| --- | --- | --- |
| Username | `neo4j` | Tài khoản quản trị ban đầu |
| Password | Mật khẩu do bạn tạo | Không ghi mật khẩu thật trong Git, log, báo cáo |
| Database | `neo4j` | Database thường có sẵn trong lab; xác nhận tên thực tế |
| Browser URL | `http://localhost:7474/browser/` | Tải giao diện web, không phải URI Driver |
| Bolt URI | `bolt://localhost:7687` | Địa chỉ Java Driver/Cypher Shell kết nối vào DBMS local |
| AuraDB URI | `neo4j+s://<instance-id>.databases.neo4j.io` | Sao chép nguyên URI từ Aura Console; dùng TLS |

### 2.2. Vòng đời mật khẩu khởi tạo

~~~mermaid
flowchart TD
    A["Cài DBMS mới, chưa có dữ liệu user"] --> B{"Đã đặt mật khẩu ban đầu?"}
    B -- "Có" --> C["Neo4j khởi tạo native user bằng credential đó"]
    B -- "Chưa" --> D["Local server dùng neo4j / neo4j<br/>và yêu cầu đổi ở lần đăng nhập đầu"]
    C --> E["Đăng nhập lần đầu"]
    D --> E
    E --> F{"Có yêu cầu đổi mật khẩu?"}
    F -- "Có" --> G["Đổi sang mật khẩu riêng"]
    F -- "Không" --> H["Truy vấn và xác minh kết nối"]
    G --> H
    H --> I["Khi cần đổi tiếp: dùng ALTER CURRENT USER"]
    I --> J["Ứng dụng cập nhật secret và tạo lại kết nối"]
~~~

**Nguyên tắc cốt lõi:** “Đặt mật khẩu ban đầu” là thao tác **khởi tạo tài khoản trên DBMS mới**, còn “đổi mật khẩu” tác động tới tài khoản **đã tồn tại**. Hai thao tác không thay thế nhau.

- Với server tự cài, `neo4j-admin dbms set-initial-password` chỉ dùng **trước khi DBMS khởi động lần đầu**.
- Với Docker, `NEO4J_AUTH` hoặc `NEO4J_AUTH_FILE` chỉ dùng để khởi tạo user khi **volume `/data` chưa có trạng thái xác thực**.
- Khi database đã tồn tại, thay biến môi trường, file secret hoặc chạy lại container **không ghi đè** mật khẩu user đang lưu.
- Trong Neo4j server tự cài, nếu không đặt trước, mật khẩu mặc định là `neo4j` và người dùng phải đổi khi đăng nhập lần đầu. **Không để nguyên credential mặc định** trên một endpoint có thể truy cập từ mạng khác.

## 3. Chuẩn bị trước khi tạo tài khoản

Xác định môi trường bạn đang dùng:

| Môi trường | Ai tạo mật khẩu lần đầu? | Nơi kết nối |
| --- | --- | --- |
| **Neo4j Desktop** | Người dùng khi tạo DBMS qua UI | DBMS cục bộ do Desktop quản lý |
| **Server cài native (ZIP/TAR/DEB/RPM)** | Lệnh `neo4j-admin` **trước lần start đầu**, hoặc đổi từ mặc định ở lần login đầu | `bolt://localhost:7687` nếu cài mặc định |
| **Docker/Compose** | `NEO4J_AUTH` hoặc file được `NEO4J_AUTH_FILE` chỉ tới | Host: `bolt://localhost:7687` nếu publish; cùng Compose network: `bolt://neo4j:7687` |
| **AuraDB** | Dịch vụ cung cấp credential ban đầu tại Aura Console | `neo4j+s://...` của instance |

Ngoài môi trường, chuẩn bị một **mật khẩu mạnh và duy nhất**, công cụ lưu bí mật có kiểm soát, URI/port, username và database name. Neo4j có chính sách mật khẩu tối thiểu; tài liệu hiện hành quy định mặc định **ít nhất 8 ký tự**, nhưng đối với sử dụng thực tế nên tạo chuỗi ngẫu nhiên dài hơn và không tái sử dụng mật khẩu của tài khoản khác.

**Bảo vệ thông tin nhạy cảm từ đầu:**

- Không ghi mật khẩu thật vào `compose.yaml`, `application.properties` trong Git, ví dụ tài liệu, ảnh chụp màn hình hoặc các ticket hỗ trợ.
- Cân nhắc rủi ro khi truyền mật khẩu bằng tham số command line: nó có thể đi vào **shell history**, danh sách tiến trình hoặc log.
- `.env` và file Compose secret trên máy phát triển **không tự động là kho bí mật đã mã hóa**; giới hạn quyền truy cập file và dùng secret manager phù hợp cho production.
- Khi cấu hình kết nối từ xa, phải đánh giá **TLS và firewall** bên cạnh username/password.

## 4. Thiết lập mật khẩu ban đầu cho Neo4j Server tự cài

### 4.1. Cách khởi tạo bằng `neo4j-admin`

Trường hợp này dành cho **DBMS mới, chưa từng được khởi động**. Sau khi cài gói Neo4j và trước khi chạy server:

~~~text
neo4j-admin dbms set-initial-password --require-password-change "<TEMPORARY_PASSWORD>"
~~~

Thay `<TEMPORARY_PASSWORD>` bằng một mật khẩu tạm đủ mạnh. Đây là **cú pháp minh họa**, không dán nguyên placeholder để dùng thật. Tùy cách cài đặt, lệnh `neo4j-admin` nằm trong thư mục `bin`, hoặc đã có trong `PATH`.

Tùy chọn `--require-password-change` khiến tài khoản phải đổi mật khẩu ở lần đăng nhập đầu, phù hợp khi quản trị viên tạo credential tạm và bàn giao cho người dùng. Nếu **không dùng** cờ đó, lệnh đặt mật khẩu ban đầu theo mặc định không yêu cầu đổi ngay; điều này khác với trường hợp server dùng mật khẩu mặc định `neo4j`.

Với Linux cài từ package quản lý bằng `systemd`, có thể cần chạy lệnh dưới danh tính tài khoản service `neo4j`. Ví dụ cách gọi trước khi chạy service:

~~~bash
# Vi du cho Linux package; dung password tam theo quy trinh bao mat cua ban
sudo -u neo4j neo4j-admin dbms set-initial-password --require-password-change "<TEMPORARY_PASSWORD>"
sudo systemctl start neo4j
sudo systemctl status neo4j
~~~

Mật khẩu nằm trong argument của ví dụ trên có thể bị lưu vào lịch sử lệnh. Ở môi trường dùng chung, hãy dùng cách nhập secret kín được tổ chức cho phép hoặc giao diện tương tác an toàn theo [hướng dẫn Set an initial password](https://neo4j.com/docs/operations-manual/current/configuration/set-initial-password/). Không chép một mật khẩu thật vào nội dung bài học hoặc lệnh shell được commit.

Nếu dùng ZIP/TAR, trong thư mục Neo4j tương ứng có thể gọi công cụ từ `bin` và khởi động `bin/neo4j console`; trên Windows trình chạy tương ứng nằm trong `bin` của bản cài. Đường dẫn/đuôi file thực tế phụ thuộc gói và hệ điều hành.

### 4.2. Nếu server đã khởi động lần đầu thì sao?

**Không** dùng lại `set-initial-password` để đổi mật khẩu của database hiện hữu. Khi đã đăng nhập được, dùng cách ở mục 7. Khi mất mật khẩu, dùng quy trình **password recovery** được Neo4j hỗ trợ cho phiên bản/edition của DBMS; không xóa thư mục `data` hoặc tạo volume mới chỉ để “đặt lại mật khẩu”.

**Trường hợp không cấu hình ban đầu:** ở server tự cài mới hoàn toàn, tài khoản mặc định là `neo4j` với mật khẩu `neo4j` và phải đổi ngay khi đăng nhập đầu tiên. Không thử credential mặc định trên một hệ thống không thuộc quyền quản trị của bạn.

## 5. Khởi tạo tài khoản khi dùng Neo4j Desktop

Neo4j Desktop hỗ trợ tạo và vận hành DBMS local thông qua giao diện. Quy trình chung:

1. Cài Desktop tương thích với OS, tạo một **local DBMS instance** và chọn phiên bản DBMS.
2. Khi Desktop yêu cầu, đặt mật khẩu cho **user `neo4j`**. Lưu mật khẩu trong công cụ quản lý bí mật cá nhân.
3. **Start** DBMS, theo dõi trạng thái và log cho tới khi service sẵn sàng.
4. Mở công cụ **Query/Neo4j Browser** từ Desktop, kết nối vào đúng DBMS.
5. Chạy `SHOW CURRENT USER;` và `RETURN 1 AS ok;` để kiểm tra phiên xác thực và truy vấn.

Tên nút có thể thay đổi giữa các bản Desktop; hãy tìm phần quản lý **DBMS/connection**. **Phiên bản Desktop** không đồng nghĩa phiên bản **Neo4j Server** bên trong, và mỗi local DBMS có credential riêng. Nếu có nhiều DBMS cục bộ, hãy đối chiếu đúng tên instance/port trước khi nghi ngờ mật khẩu sai.

Khi muốn đổi mật khẩu của tài khoản đã đăng nhập, dùng Cypher ở mục 7. Không xóa DBMS hoặc thư mục database chỉ vì quên mật khẩu.

## 6. Khởi tạo user với Docker Compose và secret

### 6.1. Cấu hình Compose dùng volume giữ dữ liệu

Docker image Neo4j chính thức hỗ trợ `NEO4J_AUTH` và **`NEO4J_AUTH_FILE`**. Ví dụ dưới đây dùng **Compose secret** để tránh đặt password trực tiếp vào file YAML.

Tạo thư mục lab chứa:

~~~text
neo4j-auth-lab/
├── compose.yaml
├── .gitignore
└── secrets/
    └── neo4j_auth.txt
~~~

Nội dung `compose.yaml`:

~~~yaml
services:
  neo4j:
    image: neo4j:2026.10.2
    ports:
      - "127.0.0.1:7474:7474"
      - "127.0.0.1:7687:7687"
    environment:
      NEO4J_AUTH_FILE: /run/secrets/neo4j_auth
    secrets:
      - neo4j_auth
    volumes:
      - neo4j_data:/data
    restart: unless-stopped

secrets:
  neo4j_auth:
    file: ./secrets/neo4j_auth.txt

volumes:
  neo4j_data:
~~~

File `secrets/neo4j_auth.txt` có **một dòng**:

~~~text
neo4j/REPLACE_WITH_A_UNIQUE_STRONG_PASSWORD
~~~

Thay placeholder thành mật khẩu riêng trước khi khởi động. Neo4j đọc file secret trong container tại `/run/secrets/neo4j_auth`. `neo4j` là **username khởi tạo**; phần phía sau dấu `/` là password. Nếu có dấu đặc biệt hoặc ký tự không ASCII, hãy bảo đảm file đúng UTF-8 và kiểm tra hướng dẫn định dạng secret cho bản Neo4j đang dùng.

Thêm `secrets/` vào `.gitignore`:

~~~gitignore
secrets/
.env
.env.*
!.env.example
~~~

**Lưu ý:** Docker Compose local mount secret dưới dạng file. Nội dung file vẫn hiện cho những người có quyền đọc thích hợp trên host; đây là cơ chế truyền secret vào container, **không thay thế vault/secret manager**.

### 6.2. Chạy và đăng nhập lần đầu

Trong thư mục `neo4j-auth-lab`:

~~~bash
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Đợi Neo4j sẵn sàng rồi mở `http://localhost:7474/browser/`, dùng:

- **Bolt URI:** `bolt://localhost:7687`.
- **Username:** `neo4j`.
- **Password:** chuỗi sau `neo4j/` trong secret đã tạo.

Cổng host được giới hạn ở `127.0.0.1` cho mục đích lab cục bộ. Nếu ứng dụng Java chạy **trong service khác cùng Compose network**, URI bên trong mạng là `bolt://neo4j:7687`.

### 6.3. Vì sao đổi file secret không đổi mật khẩu đã lưu?

File `NEO4J_AUTH_FILE` chỉ thiết lập **initial authentication** khi Neo4j chưa có database user. Ở ví dụ trên, trạng thái xác thực và dữ liệu nằm trong volume được mount tại `/data`.

Ví dụ tình huống:

1. Lần đầu khởi động bằng secret mật khẩu A: Neo4j tạo credential A.
2. Bạn tạo node/relationship, dừng bằng `docker compose down`: **volume vẫn tồn tại**.
3. Bạn sửa secret thành mật khẩu B rồi chạy `docker compose up -d`.
4. Neo4j dùng lại auth đã tồn tại trong volume: **B không thay thế A**. Phải đăng nhập bằng mật khẩu còn hiệu lực và đổi nó theo mục 7.

**Không dùng** `docker compose down -v` như một cách “reset password”: cờ `-v` có thể xóa named volume chứa dữ liệu graph, user và metadata. Muốn giữ dữ liệu phải giữ đúng project name, đúng volume và dùng quy trình đổi/khôi phục mật khẩu.

## 7. Đổi mật khẩu của tài khoản đang đăng nhập

### 7.1. Đổi khi Neo4j yêu cầu ở lần đăng nhập đầu

Nếu hệ thống báo **password change required**, hãy làm theo màn hình đổi mật khẩu của công cụ bạn đang dùng; nhập mật khẩu tạm hiện tại, chọn mật khẩu mới, rồi đăng nhập lại.

Sau khi đổi thành công, cập nhật mật khẩu ở nơi lưu secret và ở các ứng dụng phụ thuộc. Một ứng dụng Java đang giữ credential cũ có thể tiếp tục báo `Authentication failed` cho các kết nối mới cho đến khi cấu hình và Driver được tạo lại.

### 7.2. Đổi mật khẩu bằng Cypher

Người dùng **đã đăng nhập** có thể đổi mật khẩu của chính mình mà không cần đặc quyền quản trị user khác:

~~~cypher
ALTER CURRENT USER
SET PASSWORD FROM '<CURRENT_PASSWORD>' TO '<NEW_STRONG_PASSWORD>';
~~~

`<CURRENT_PASSWORD>` và `<NEW_STRONG_PASSWORD>` là **placeholder**, không phải giá trị để dùng trong môi trường thật. Lệnh cần mật khẩu cũ chính xác và mật khẩu mới đáp ứng chính sách. Mật khẩu mới phải khác mật khẩu trước đó. Đây là **thay đổi credential của user hiện tại**, không tạo một account mới.

Với ứng dụng có API truyền tham số Cypher, nên dùng **string parameters** thay cho chèn trực tiếp mật khẩu thật vào chuỗi truy vấn:

~~~cypher
ALTER CURRENT USER
SET PASSWORD FROM $currentPassword TO $newPassword;
~~~

Hai giá trị `$currentPassword`, `$newPassword` do client cung cấp một cách an toàn theo công cụ sử dụng; truy vấn này **không chạy được khi chưa truyền đủ tham số**. Nếu dùng Browser hoặc Cypher Shell, quy trình truyền tham số có thể khác nhau giữa phiên bản. Tránh dán mật khẩu thật vào truy vấn được lưu trong lịch sử/browser, ảnh chụp hoặc log.

Để xác minh user và trạng thái yêu cầu đổi mật khẩu:

~~~cypher
SHOW CURRENT USER;
~~~

Kết quả thường có các cột `user` và `passwordChangeRequired`; các cột bổ sung như `roles` hoặc `suspended` có thể khác theo edition. Sau khi đổi, hãy **ngắt kết nối và đăng nhập lại bằng mật khẩu mới**. Một phiên đã xác thực từ trước có thể còn tồn tại; kiểm chứng cần dựa trên **phiên đăng nhập mới**, không chỉ dựa vào việc câu lệnh đổi mật khẩu trả thành công.

### 7.3. Đổi mật khẩu người dùng khác và quyền quản trị

Trong môi trường có chức năng quản lý user và quyền quản trị phù hợp, một quản trị viên có thể đặt lại mật khẩu cho tài khoản được quản lý bằng lệnh `ALTER USER`. Ví dụ cú pháp:

~~~cypher
ALTER USER someUser SET PASSWORD '<NEW_TEMPORARY_PASSWORD>' CHANGE REQUIRED;
~~~

Đây là **thao tác quản trị**: quyền thực thi phụ thuộc edition, cấu hình xác thực và quyền DBMS. Không dùng nó thay cho `ALTER CURRENT USER` khi người dùng biết mật khẩu cũ và chỉ muốn tự đổi mật khẩu. Khi bàn giao mật khẩu tạm cho người khác, yêu cầu đổi ở lần đăng nhập kế tiếp và dùng kênh truyền credential được phê duyệt.

### 7.4. Nếu đã quên hoàn toàn mật khẩu thì sao?

Không thể tự đổi bằng `ALTER CURRENT USER` khi không đăng nhập được. Trình tự xử lý phù hợp:

1. Xác nhận đúng **instance, URI, port và username**, vì nhầm máy thường bị tưởng thành quên mật khẩu.
2. Kiểm tra mật khẩu trong kho bí mật hoặc quy trình bàn giao nội bộ; không liên tục đoán mật khẩu khiến tài khoản bị giới hạn sau nhiều lần sai.
3. Nếu có người quản trị khác được phân quyền, yêu cầu người đó thực hiện thao tác reset phù hợp.
4. Nếu không còn quyền quản trị, sử dụng quy trình **[Recover admin user and password](https://neo4j.com/docs/operations-manual/current/authentication-authorization/password-and-user-recovery/)** của **đúng phiên bản và edition**, trên hệ thống bạn sở hữu/quản trị.

Quy trình khôi phục có thể cần thao tác bảo trì và cô lập mạng; hãy làm theo tài liệu Neo4j để tránh mở database không xác thực ra ngoài. **Không** xóa volume `/data`, tắt authentication lâu dài hoặc thay mật khẩu khởi tạo với kỳ vọng ghi đè auth hiện có.

## 8. AuraDB: credential do dịch vụ cấp

**Neo4j AuraDB** chạy trên hạ tầng được quản lý. Bạn **không sử dụng `neo4j-admin dbms set-initial-password` trên AuraDB**, vì không có quyền quản lý trực tiếp file system/process của dịch vụ.

Quy trình ban đầu:

1. Truy cập **[Aura Console](https://console.neo4j.io/)**, tạo hoặc chọn AuraDB instance.
2. Nhận/download thông tin kết nối do dịch vụ cung cấp: **Connection URI**, **username**, **password** và tên database nếu cần.
3. Lưu password/credential vào kho bí mật được chấp thuận. Một số credential được hiển thị để tải **chỉ tại thời điểm tạo**, nên hãy lưu an toàn ngay.
4. Dùng công cụ **Query** trong Aura Console hoặc Java Driver để kết nối bằng URI được cấp, thường dạng:

~~~text
neo4j+s://example123.databases.neo4j.io
~~~

`example123` chỉ là placeholder; **không tự suy ra hostname**, không đổi `neo4j+s://` thành `bolt://` để bỏ qua TLS. Khi cần reset/rotate credential và không đăng nhập được, dùng chức năng/quy trình chính thức trong Aura Console hoặc hỗ trợ dịch vụ theo tier. Khi đang đăng nhập bằng native auth, lệnh đổi mật khẩu hiện tại có thể áp dụng tùy khả năng/điều khoản dịch vụ.

## 9. Kiểm tra kết nối theo từng cấp độ

Kiểm tra nên tách **mạng → giao thức → xác thực → database → Cypher**. Nếu chỉ mở được trang Browser, chưa thể kết luận tài khoản đã đăng nhập thành công.

### 9.1. Cấp độ 1: DBMS và cổng có sẵn sàng?

Với Docker Compose:

~~~bash
docker compose ps
docker compose logs --tail=100 neo4j
~~~

Với Desktop, xem trạng thái và log của instance đang dùng. Với server native trên Linux, có thể xem `systemctl status neo4j` và `journalctl -u neo4j` nếu dùng systemd.

Hai cổng thường gặp:

| Port / URI | Vai trò | Điều kiểm tra |
| --- | --- | --- |
| `http://localhost:7474/browser/` | Giao diện web Neo4j Browser | Browser tải được trang |
| `bolt://localhost:7687` | Truy vấn bằng Bolt | Driver/Cypher Shell đến đúng DBMS |
| `neo4j+s://<id>.databases.neo4j.io` | AuraDB qua Bolt TLS | DNS, mạng, TLS và credential |

Nếu Java chạy trong **container khác** cùng Compose network, `localhost` trỏ về **container Java**, không trỏ sang service Neo4j. Khi đó thường dùng `bolt://neo4j:7687`, với `neo4j` là service DNS.

### 9.2. Cấp độ 2: đăng nhập qua Neo4j Browser

Với Neo4j local, mở `http://localhost:7474/browser/`:

1. Chọn địa chỉ Bolt của **instance** cần đăng nhập, ví dụ `bolt://localhost:7687`.
2. Nhập username `neo4j` và password đã **đổi/khởi tạo cho instance đó**.
3. Nếu công cụ yêu cầu đổi mật khẩu lần đầu, hoàn tất rồi đăng nhập lại.
4. Chạy:

~~~cypher
SHOW CURRENT USER;
~~~

Nếu trả được thông tin user, bạn đã xác thực thành công. Tiếp tục chạy:

~~~cypher
RETURN 1 AS ok, datetime() AS serverTime;
~~~

Một dòng có `ok = 1` là bằng chứng bạn đã thực thi được Cypher trên database đang chọn. Khi cần xác nhận phiên bản/edition:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Không suy ra phiên bản server chỉ từ tên image, phiên bản giao diện Browser hoặc mã ứng dụng.

### 9.3. Cấp độ 3: thử bằng Cypher Shell

Trên host có cài `cypher-shell`:

~~~bash
cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j
~~~

Với Docker Compose, chạy công cụ bên trong container Neo4j:

~~~bash
docker compose exec neo4j cypher-shell -a bolt://localhost:7687 -u neo4j -d neo4j
~~~

Nếu không truyền password qua cờ dòng lệnh, `cypher-shell` sẽ yêu cầu bạn nhập mật khẩu một cách tương tác tùy phiên bản/cấu hình. Không gắn `-p YOUR_REAL_PASSWORD` vào lệnh dùng chung, tránh rò rỉ qua history/process list.

Sau khi đăng nhập, chạy:

~~~cypher
RETURN 'authenticated' AS status;
~~~

Nếu Cypher Shell đăng nhập thành công nhưng Browser lỗi, tập trung vào cấu hình Browser, WebSocket, địa chỉ Bolt/TLS trên trình duyệt. Nếu cả hai đều thất bại, kiểm tra trạng thái DBMS, URI và credential.

### 9.4. Cấp độ 4: Neo4j Java Driver

Thư viện **Neo4j Java Driver** kết nối qua Bolt, không dùng URL HTTP của Browser. Ví dụ kiểm tra từ ứng dụng Java đã khai báo dependency Driver tương thích:

~~~java
import org.neo4j.driver.AuthTokens;
import org.neo4j.driver.Driver;
import org.neo4j.driver.GraphDatabase;
import org.neo4j.driver.Session;

public class Neo4jLoginCheck {
    public static void main(String[] args) {
        String uri = requireEnv("NEO4J_URI");
        String user = requireEnv("NEO4J_USERNAME");
        String password = requireEnv("NEO4J_PASSWORD");

        try (Driver driver = GraphDatabase.driver(
                uri, AuthTokens.basic(user, password))) {
            // Tao Driver chua dam bao ket noi; dong nay moi kiem tra server.
            driver.verifyConnectivity();

            try (Session session = driver.session()) {
                long value = session.run("RETURN 1 AS ok")
                                    .single().get("ok").asLong();
                System.out.println("Neo4j connection OK: " + value);
            }
        }
    }

    private static String requireEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing environment variable: " + key);
        }
        return value;
    }
}
~~~

Đặt biến môi trường ở nơi chạy ứng dụng; **không** hardcode credential trong Java. Ví dụ URI `bolt://localhost:7687` khi chạy ứng dụng trên host và Neo4j local; trong cùng Compose network dùng `bolt://neo4j:7687`; với AuraDB dùng đúng `neo4j+s://...`.

**Sau khi đổi mật khẩu:** cập nhật `NEO4J_PASSWORD` trong môi trường ứng dụng rồi **tạo lại Driver/kết nối**; một Driver đã khởi tạo từ `AuthTokens.basic(user, oldPassword)` không tự biết mật khẩu mới. Nếu dùng pool, Spring Boot hoặc secrets manager, thực hiện reload/restart thành phần theo thiết kế để kết nối mới dùng credential mới.

### 9.5. Cấp độ 5: Spring Data Neo4j

Khi sử dụng Spring Boot với Spring Data Neo4j, có thể cấu hình trong `application.properties`:

~~~properties
spring.neo4j.uri=${NEO4J_URI}
spring.neo4j.authentication.username=${NEO4J_USERNAME}
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

Thông số này dùng cho kết nối thông qua Driver. Cần đối chiếu phiên bản Spring Boot, Spring Data Neo4j, Driver và JDK ứng dụng; JVM của **server Neo4j** có thể chạy ở môi trường khác. Nếu ứng dụng sử dụng một database cụ thể, cấu hình tên database theo khả năng của phiên bản Spring Data Neo4j đang dùng.

## 10. Kiểm tra quyền truy cập bằng một property graph nhỏ

Truy vấn `RETURN 1` chứng minh kết nối và thực thi Cypher cơ bản; để xác nhận quyền **ghi/đọc dữ liệu**, tạo một graph nhỏ trong database **thử nghiệm**:

~~~cypher
MERGE (student:Student {studentId: 'neo4j-auth-lab'})
  ON CREATE SET student.name = 'An'
MERGE (course:Course {courseId: 'neo4j-connect'})
  ON CREATE SET course.title = 'Ket noi Neo4j'
MERGE (student)-[:ENROLLED_IN]->(course)
RETURN student.name AS studentName, course.title AS courseTitle;
~~~

Đọc lại mối liên kết:

~~~cypher
MATCH p =
  (:Student {studentId: 'neo4j-auth-lab'})
  -[:ENROLLED_IN]->
  (:Course {courseId: 'neo4j-connect'})
RETURN p;
~~~

Nếu kết quả có path với hai node và relationship `ENROLLED_IN`, ta đã kiểm tra **ghi và đọc** dữ liệu property graph. `MERGE` phù hợp với bài lab chạy lặp; với ứng dụng nhiều giao dịch đồng thời vẫn cần thiết kế **uniqueness constraint**.

Nếu `RETURN 1` thành công nhưng `MERGE` bị từ chối do thiếu quyền, kết nối **đã xác thực thành công** nhưng **user chưa có quyền ghi**. Đây là lỗi **authorization**, không phải lỗi password.

## 11. Các tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
| --- | --- | --- |
| `Authentication failed` ngay lúc đăng nhập | Nhầm username, sai password, sai instance/port | Đối chiếu URI, tên instance, password đang hiệu lực; thử Browser/Cypher Shell |
| Đổi `NEO4J_AUTH`/secret nhưng password không đổi | Volume `/data` chứa user đã tạo ở lần khởi động trước | Đăng nhập bằng credential cũ còn hiệu lực và dùng `ALTER CURRENT USER`; không xóa volume |
| `Password change required` | Đang dùng mật khẩu mặc định hoặc mật khẩu tạm bị buộc đổi | Hoàn tất quy trình đổi password, kết nối lại bằng password mới |
| `Too many failed authentication attempts` hoặc khóa đăng nhập tạm | Thử sai credential liên tiếp vượt giới hạn | Ngừng đoán password, chờ theo chính sách và kiểm tra credential đúng |
| `Connection refused` | Server chưa sẵn sàng, sai port/hostname hoặc Bolt chưa lắng nghe | Xem service/log, thử đúng `bolt://...:7687` từ nơi ứng dụng chạy |
| Browser mở trang được nhưng chưa đăng nhập được | HTTP `7474` hoạt động nhưng Bolt `7687`/WebSocket không thông hoặc auth sai | Kiểm tra URI Bolt, mạng/TLS, mật khẩu, thử Cypher Shell |
| Docker Java app dùng `localhost:7687` không kết nối | `localhost` đang trỏ về container Java | Trong cùng Compose network dùng `bolt://neo4j:7687` |
| AuraDB báo lỗi TLS/certificate | Sai scheme, CA, DNS, endpoint hoặc mạng chặn | Giữ nguyên `neo4j+s://` do Aura cấp, kiểm tra TLS và trạng thái instance |
| `Database not found` | Tên database sai hoặc database không tồn tại | Xác nhận database trong instance, không tự suy tất cả đều tên `neo4j` |
| Lệnh đọc được nhưng `CREATE`/`MERGE` bị từ chối | Tài khoản thiếu quyền ghi | Kiểm tra quyền hiện có; người quản trị cấp quyền thích hợp theo edition |
| Đổi mật khẩu thành công nhưng Spring Boot vẫn báo sai password | Ứng dụng vẫn giữ credential cũ hoặc pool/Driver chưa reload | Cập nhật secret ứng dụng và khởi tạo lại các kết nối cần thiết |
| Quên password admin, không còn ai đăng nhập được | Không có credential hợp lệ | Làm theo hướng dẫn recovery chính thức, cô lập mạng, giữ nguyên dữ liệu |

**Quy trình chẩn đoán khuyến nghị:** đúng DBMS/URI → TCP/Bolt/TLS → username/password → trạng thái đổi mật khẩu → database → quyền truy vấn. Chỉ thử lệnh thay đổi dữ liệu sau khi đã xác nhận đang ở **database lab**, tránh nhầm môi trường sản xuất.

## 12. Bảo mật tài khoản khi chuyển từ lab sang ứng dụng thực

Một tài khoản ban đầu giúp bắt đầu học nhanh nhưng không phải mô hình quản trị lâu dài. Khi đưa hệ thống đồ thị vào backend Java hoặc môi trường dùng chung:

- **Tách người dùng và ứng dụng:** nếu edition/quyền hỗ trợ, cấp tài khoản chuyên dụng cho dịch vụ với **quyền tối thiểu**, hạn chế dùng admin `neo4j` để phục vụ mọi request của ứng dụng.
- **Quản lý vòng đời secret:** chọn mật khẩu mạnh, không dùng lại; lưu trong vault hoặc cơ chế quản lý bí mật phù hợp; ghi nhận chủ sở hữu và cách rotate.
- **Thay mật khẩu có kế hoạch:** cập nhật secret các consumer, đổi password, kiểm chứng kết nối mới và dọn credential cũ theo quy trình vận hành.
- **Kết nối có mã hóa khi ra ngoài máy:** triển khai TLS và certificate trust phù hợp; AuraDB sử dụng URI `neo4j+s://`. Không dùng `bolt+ssc://` để bỏ qua xác minh chứng chỉ trên mạng công cộng.
- **Theo dõi log mà không rò rỉ:** log thông tin cần thiết để chẩn đoán như loại lỗi, instance, database, thời điểm; không in mật khẩu, token hoặc toàn bộ environment.
- **Không tắt xác thực để “sửa lỗi”:** recovery có điều kiện an toàn riêng, không biến `dbms.security.auth_enabled=false` thành một cấu hình hoạt động thường xuyên.

## 13. Bài thực hành và tiêu chí hoàn thành

### Bài tập 1 — Khởi tạo và buộc đổi mật khẩu

Trên một **DBMS mới**, chọn Desktop hoặc server native. Thiết lập mật khẩu tạm và yêu cầu đổi trong lần đăng nhập đầu (nếu cách triển khai hỗ trợ). Đăng nhập, đổi password, kết nối lại và chạy `SHOW CURRENT USER`. Giải thích sự khác nhau giữa mật khẩu tạm và mật khẩu đang có hiệu lực.

### Bài tập 2 — Docker volume giữ lại credential

Khởi động Docker Compose với `NEO4J_AUTH_FILE` và volume `/data`; tạo graph trong mục 10. Chạy `docker compose down` rồi `docker compose up -d`. Quan sát dữ liệu vẫn còn và credential cũ vẫn hiệu lực. Giải thích vì sao sửa file secret thành một password mới **không tự đặt lại** tài khoản. **Không chạy `down -v`**.

### Bài tập 3 — Đổi password và cập nhật backend

Đổi mật khẩu tài khoản Neo4j thông qua `ALTER CURRENT USER`. Sau đó cập nhật secret của ứng dụng Java/Spring Boot, tạo lại Driver/pool tương ứng, chạy `verifyConnectivity()` và `RETURN 1 AS ok`. Nêu điều gì sẽ xảy ra nếu ứng dụng vẫn dùng credential cũ.

### Bài tập 4 — Phân loại lỗi

Một sinh viên mở được `http://localhost:7474/browser/`, nhưng `SHOW CURRENT USER` thất bại do sai password. Một sinh viên khác chạy được `SHOW CURRENT USER` và `RETURN 1` nhưng `MERGE` bị từ chối. Hãy phân biệt lỗi **authentication** và **authorization**, đồng thời nêu bước kiểm tra phù hợp cho mỗi trường hợp.

### Checklist nghiệm thu

- [ ] Biết tên user ban đầu và phân biệt user với database.
- [ ] Biết khi nào dùng `set-initial-password`, khi nào dùng `ALTER CURRENT USER`.
- [ ] Có credential mạnh, riêng biệt và được lưu an toàn.
- [ ] Đăng nhập được qua Browser hoặc Cypher Shell, chạy `SHOW CURRENT USER`.
- [ ] Đổi password thành công và **đăng nhập lại** bằng mật khẩu mới.
- [ ] Đối chiếu đúng URI, port, Bolt/TLS và tên database.
- [ ] Kiểm tra được `RETURN 1` và một graph đọc/ghi trong database thử nghiệm.
- [ ] Biết mật khẩu trong Docker volume không đổi khi sửa `NEO4J_AUTH_FILE`.
- [ ] Cập nhật credential của Java/Spring Boot sau khi rotate.
- [ ] Không đưa mật khẩu, file secret hoặc thông tin nhạy cảm lên Git.

## 14. Nguồn tham khảo chính thức

- [Neo4j Operations Manual — Set an initial password](https://neo4j.com/docs/operations-manual/current/configuration/set-initial-password/) — lệnh `neo4j-admin dbms set-initial-password` và yêu cầu đổi mật khẩu.
- [Neo4j Operations Manual — Manage users](https://neo4j.com/docs/operations-manual/current/authentication-authorization/manage-users/) — `SHOW CURRENT USER`, `ALTER CURRENT USER SET PASSWORD`, quản lý user.
- [Neo4j Operations Manual — Getting started with Docker](https://neo4j.com/docs/operations-manual/current/docker/introduction/) — `NEO4J_AUTH`, trạng thái authentication khi có volume cũ.
- [Neo4j Operations Manual — Docker Compose](https://neo4j.com/docs/operations-manual/current/docker/docker-compose-standalone/) — secret file và `NEO4J_AUTH_FILE`.
- [Neo4j Operations Manual — Recover admin user and password](https://neo4j.com/docs/operations-manual/current/authentication-authorization/password-and-user-recovery/) — trường hợp mất quyền quản trị.
- [Neo4j Java Driver Manual — Connection](https://neo4j.com/docs/java-manual/current/connect/) — khởi tạo Driver và kiểm tra `verifyConnectivity()`.
- [Neo4j Browser Manual](https://neo4j.com/docs/browser-manual/current/) — đăng nhập và chạy Cypher bằng giao diện.
- [Neo4j Aura documentation](https://neo4j.com/docs/aura/) — kết nối/credential của dịch vụ quản lý.

**Điều cần nhớ:** Hãy xử lý **mật khẩu khởi tạo** và **mật khẩu đã lưu trong DBMS** như hai trạng thái khác nhau. Việc đổi credential phải được xác minh bằng **một lần đăng nhập mới**, sau đó thử Cypher và cập nhật mọi ứng dụng phụ thuộc. Dữ liệu trong graph và thông tin xác thực đều cần được bảo vệ khi thay đổi môi trường.
