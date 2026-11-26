# Cài đặt Neo4j và kiểm tra yêu cầu hệ thống theo phiên bản

## 1. Mục tiêu của bài học

**Neo4j** là hệ quản trị cơ sở dữ liệu đồ thị dựa trên mô hình **property graph**: thông tin nằm trong các **node**, các **relationship** có hướng nối node, và các **property** mô tả chúng. Ngôn ngữ **Cypher** cho phép truy vấn quan hệ, mẫu kết nối và đường đi. Để học tiếp về index, constraint, nhập dữ liệu, tối ưu truy vấn hay kết nối bằng Java Driver và Spring Data Neo4j, trước tiên ta cần **cài được đúng phiên bản Neo4j trên môi trường tương thích**.

Kết thúc bài học, bạn có thể:

1. Phân biệt phiên bản **DBMS Neo4j**, phiên bản **Cypher**, phiên bản **JVM chạy server** và phiên bản **Java Driver chạy trong ứng dụng**.
2. Đối chiếu phiên bản Neo4j với hệ điều hành, kiến trúc CPU, Java, RAM và dung lượng lưu trữ.
3. Chọn gói tải chính thức, xác minh phiên bản/edition và khởi động Neo4j qua Desktop, gói server hoặc Docker.
4. Kiểm tra dịch vụ bằng Browser, Cypher và log; xác định nguyên nhân khi không khởi động được.
5. Lập một biên bản cài đặt có thể dùng lại khi thực hành Java/Spring Boot.

> **Mốc tài liệu:** Các ví dụ cụ thể trong bài đối chiếu tài liệu Neo4j **2026.10.2** (phát hành tháng 11/2026). Đây là **phiên bản minh họa có chủ đích**, không phải yêu cầu luôn phải dùng bản mới nhất. Khi chạy dự án thực tế, hãy tra tài liệu đúng phiên bản đã chọn, đặc biệt khi chính sách hỗ trợ OS/JVM thay đổi.

## 2. Hiểu đúng “phiên bản Neo4j” trước khi cài

### 2.1. Neo4j Server sử dụng hai kiểu đánh số

- Các nhánh cũ có dạng **4.4**, **5.x**, ví dụ **5.26 LTS**.
- Từ **2025.01**, Neo4j Server dùng lịch phát hành **CalVer** với dạng **YYYY.MM.Patch**, ví dụ `2026.10.2`. Tên này chỉ thời điểm phát hành và bản sửa lỗi; không được hiểu `2026.10` là “Java 26” hoặc “Cypher 26”.
- Một số bản được chỉ định là **LTS (Long-Term Support)**; cần xem vòng đời hỗ trợ và hướng dẫn nâng cấp khi chọn giữa LTS với bản phát hành mới.
- **Community Edition** và **Enterprise Edition** có tính năng/quyền sử dụng khác nhau. Không suy ra một lệnh có thể chạy trên mọi edition chỉ vì cùng phiên bản server.

### 2.2. Ma trận Neo4j Server ↔ Java cho bản cài trực tiếp

Theo [Neo4j Operations Manual – System requirements](https://neo4j.com/docs/operations-manual/current/installation/requirements/):

| Phiên bản Neo4j Server | JVM phù hợp theo nhánh | Ghi chú |
| --- | --- | --- |
| **2025.10 trở lên**, gồm **2026.10.2** | **Java 21 hoặc Java 25** | Chọn một bản Java được Neo4j hỗ trợ trên đúng OS |
| **2025.01 đến trước 2025.10** | **Java 21** | Java 17 không đáp ứng yêu cầu |
| **5.14 đến 5.26 LTS** | **Java 17 hoặc Java 21** | Kiểm tra thêm release cụ thể và OS |
| **5.x trước 5.14** | **Java 17** | Các mốc Java mới hơn cần xác nhận bằng tài liệu bản đó |
| **4.x** | **Java 11** | Nhánh cũ; không chọn cho dự án mới nếu không có lý do tương thích |
| **3.x** | **Java 8** | Chỉ đề cập để nhận diện môi trường kế thừa |

**Ví dụ đối chiếu:**

- Máy có **Java 17**, muốn cài **Neo4j 2026.10.2** từ ZIP/TAR: **không đạt**. Cài Java 21/25 phù hợp OS, hoặc chọn một bản Neo4j tương thích với yêu cầu dự án.
- Máy có **Java 21**, muốn chạy **Neo4j 5.26 LTS** hoặc **2026.10.2**: yêu cầu **major Java** phù hợp cho cả hai; vẫn phải kiểm tra OS, kiến trúc CPU và vendor JDK.
- Dự án Java có ứng dụng chạy trên **Java 17** và DBMS Neo4j 2026 chạy ở một máy/tiến trình khác bằng **Java 21**: **có thể hợp lệ** nếu phiên bản Java Driver của ứng dụng hỗ trợ Neo4j Server. Không buộc cả hai tiến trình dùng cùng JVM.

> **Ba yếu tố tách biệt:** `java -version` trên host cho biết Java trong terminal; DBMS Neo4j sử dụng JVM đã cấu hình cho **tiến trình server**; ứng dụng Java sử dụng JVM riêng và **Java Driver** riêng. Neo4j Desktop có cơ chế cung cấp JDK cho DBMS mà nó quản lý; image Docker cũng có runtime được đóng gói, nên không nhất thiết phải cài Java 21 trên host để chạy container.

### 2.3. Đừng nhầm phiên bản Cypher và DBMS

Từ **Neo4j 2025.06**, Neo4j có các phiên bản ngôn ngữ **Cypher 5** và **Cypher 25**. Cấu hình có thể chọn phiên bản mặc định cho DBMS/database; truy vấn cũng có thể chỉ định tường minh:

~~~cypher
CYPHER 5
RETURN 'Chay bang Cypher 5' AS result;
~~~

Từ **2026.02**, file cấu hình `neo4j.conf` phân phối mặc định đặt `db.query.default_language=CYPHER_25` cho database mới. Database đang có có thể vẫn giữ cấu hình ngôn ngữ của nó. Khi học cú pháp hoặc nhập dữ liệu từ dự án cũ, hãy ghi nhận **cả phiên bản DBMS và Cypher** để giải thích khác biệt về cú pháp/hành vi. Xem [Neo4j Operations Manual – Introduction](https://neo4j.com/docs/operations-manual/current/introduction/) và [Configure Cypher version](https://neo4j.com/docs/operations-manual/current/configuration/cypher-version-configuration/).

## 3. Kiểm tra yêu cầu hệ thống trước khi tải

### 3.1. Quy trình preflight theo đúng thứ tự

~~~mermaid
flowchart TD
  A["Xác định Neo4j version / edition"] --> B["Chọn cách triển khai"]
  B --> C{"Desktop hoặc Docker?"}
  C -- "Có" --> D["Đối chiếu yêu cầu Desktop/Docker và tài nguyên host"]
  C -- "Server native" --> E["Đối chiếu OS, CPU, JDK theo phiên bản"]
  D --> F["Kiểm tra RAM, đĩa, port và quyền ghi"]
  E --> F
  F --> G{"Mọi điều kiện đạt?"}
  G -- "Không" --> H["Cập nhật môi trường hoặc chọn bản tương thích"]
  H --> B
  G -- "Có" --> I["Tải gói đúng edition và kiến trúc, cài và xác minh"]
~~~

Trước tiên ghi ra bốn thông tin: **phiên bản dự định cài**, **Community/Enterprise**, **hình thức chạy (Desktop/native/Docker)** và **OS + CPU**. Sau đó mới kiểm tra Java, vì yêu cầu Java của bản server tự cài khác với Desktop/Docker.

### 3.2. Yêu cầu CPU, RAM và dung lượng

Theo [bảng System requirements](https://neo4j.com/docs/operations-manual/current/installation/requirements/), Neo4j hỗ trợ nền tảng **x86_64** và **ARM** trong những cấu hình được liệt kê:

| Loại môi trường | CPU, RAM, lưu trữ tham khảo | Ý nghĩa thực hành |
| --- | --- | --- |
| **Cá nhân/phát triển** | Tối thiểu tham khảo **2 GB RAM**, **10 GB dung lượng**; **16 GB RAM trở lên** được khuyến nghị | Cần dự phòng RAM cho hệ điều hành, Docker/IDE, ứng dụng và page cache |
| **Server tự quản lý** | Tối thiểu tham khảo **8 GB RAM**; cấu hình thực tế tùy khối lượng dữ liệu/tải | Cần tính heap, page cache, file descriptor, I/O, backup |
| **Máy cloud tự quản lý** | Tối thiểu tham khảo **2 vCPU, 2 GB RAM, 10 GB storage** | Chỉ là mức khởi điểm, không phải sizing cho production |

Neo4j thường hưởng lợi từ **SSD/NVMe**, vì nhiều tác vụ đọc ngẫu nhiên. “Đủ 10 GB ổ đĩa” không bảo đảm đủ dung lượng cho dữ liệu, transaction log, import, backup. Với máy chạy Docker Desktop, nhớ tính phần RAM được cấp cho máy ảo/engine Docker.

### 3.3. Hệ điều hành và JVM được hỗ trợ

Trong tài liệu của nhánh **2026.10.2**, ví dụ các hệ điều hành phát triển được liệt kê gồm **Windows 11**, **macOS 13/14/15/26**, **Ubuntu Desktop 22.04/24.04/26.04 LTS**, **Debian 11/12/13**. Hệ điều hành server có danh sách hỗ trợ **riêng** (chẳng hạn Windows Server 2022/2025 và các bản phân phối Linux tương ứng). Một số OS cũ đã có trạng thái **deprecated** và có thể bị bỏ hỗ trợ ở bản sau.

**Điểm quan trọng:** Không chỉ nhìn `java -version` thấy số 21/25 rồi kết luận đạt. Hãy tra **tổ hợp OS + nhà cung cấp JDK (Oracle, OpenJDK, Zulu, Temurin, ...)** trong bảng tương ứng của phiên bản Neo4j. Ví dụ: bảng Windows 11 của 2026.10.2 liệt kê **OracleJDK/ZuluJDK 21/25**, trong khi nhiều bản Linux liệt kê thêm OpenJDK/Temurin.

### 3.4. Lệnh thu thập thông tin máy

**Linux (Ubuntu/Debian/RHEL):**

~~~bash
cat /etc/os-release     # Ten va version cua he dieu hanh
uname -m                # x86_64, aarch64, ...
java -version           # Neu cai Neo4j Server native
free -h                 # RAM
df -h .                 # Dung luong phan vung hien tai
~~~

**macOS (Terminal):**

~~~bash
sw_vers                 # Phien ban macOS
uname -m                # arm64 hoac x86_64
java -version           # JVM hien tai, neu co
sysctl -n hw.memsize    # RAM tinh theo byte
df -h .                 # Dung luong o dia
~~~

**Windows (PowerShell):**

~~~powershell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture
Get-CimInstance Win32_ComputerSystem | Select-Object TotalPhysicalMemory
java -version
Get-PSDrive -PSProvider FileSystem
~~~

Nếu chưa cài Java, `java -version` báo không nhận lệnh là bình thường với Desktop/Docker; đối với **server native**, cần cài JVM thích hợp trước khi khởi động. Để biết Java **nào** đang được dùng khi máy có nhiều JDK, kiểm tra thêm `where.exe java` (Windows) hoặc `which java` (Linux/macOS), rồi xác minh `JAVA_HOME`/biến môi trường của service.

### 3.5. Kiểm tra cổng, file system và quyền

Neo4j thường cung cấp giao diện HTTP tại `localhost:7474` và kết nối Driver qua **Bolt tại `localhost:7687`**. Port này có thể thay đổi qua cấu hình. Trước khi khởi động instance thứ hai, kiểm tra liệu port đã bị chiếm:

~~~bash
# Linux: xem cac port TCP dang lang nghe
ss -lnt
~~~

~~~powershell
# Windows PowerShell
Get-NetTCPConnection -State Listen -LocalPort 7474,7687 -ErrorAction SilentlyContinue
~~~

Với bản cài trực tiếp, người chạy Neo4j cần quyền đọc cấu hình và ghi vào **data, logs, transaction logs**. Trên Linux, tài liệu hỗ trợ **EXT4/XFS** cho các cấu hình liên quan, yêu cầu tính năng flush đúng để bảo đảm ACID; không đặt database trên network share tùy tiện. Trên Windows dùng hệ thống file mặc định được hỗ trợ, **không dùng FAT**. Với Docker, quyền của thư mục bind mount/volume phải cho phép tiến trình trong container ghi dữ liệu.

## 4. Chọn nguồn tải và quản lý phiên bản

Tải **Neo4j DBMS** từ [Neo4j Deployment Center](https://neo4j.com/deployment-center/) hoặc kho package/container do Neo4j công bố. Chọn đúng **edition**, **gói cho hệ điều hành**, **kiến trúc CPU** và **phiên bản**. Trước khi triển khai:

1. Ghi phiên bản đầy đủ, ví dụ `2026.10.2` hoặc `5.26.x`; tránh để `latest` tự thay đổi môi trường học/test.
2. Đối chiếu danh sách hỗ trợ và phát hành của **phiên bản đó**; bản DBMS mới không bảo đảm tự mở được data store của bản cũ nếu bỏ qua quy trình nâng cấp.
3. Nếu tải ZIP/TAR/DEB/RPM, kiểm tra **SHA-256** đối chiếu checksum công bố trên trang tải trước khi cài.
4. Tôn trọng giấy phép edition. **Enterprise Edition** cần thỏa điều kiện giấy phép; bản Developer đi kèm Desktop chỉ dùng cho mục đích phát triển theo điều khoản tương ứng.

Kiểm tra checksum ví dụ:

~~~bash
# Linux (thay filename bang tep da tai)
sha256sum neo4j-package.tar.gz
~~~

Trên **macOS**, có thể dùng `shasum -a 256 neo4j-package.tar.gz` để tính cùng loại hash.

~~~powershell
# Windows PowerShell
Get-FileHash .\neo4j-package.zip -Algorithm SHA256
~~~

Đối chiếu toàn bộ chuỗi hash với giá trị chính thức; đây là thao tác xác minh nguồn tải, **không** tự chứng minh một gói bất kỳ đã được ký số hợp lệ.

## 5. Cài bằng Neo4j Desktop (phù hợp người mới học)

Neo4j Desktop 2.x hỗ trợ quản lý nhiều DBMS cục bộ có phiên bản khác nhau và kết nối từ xa. Desktop cung cấp JDK tương ứng cho DBMS nó quản lý; không cần tự cấu hình JVM host giống một server native. Tuy nhiên, vẫn phải kiểm tra hệ điều hành/tài nguyên tương thích **với cả Desktop và DBMS định chạy**.

### Các bước

1. Tải Desktop từ trang [Neo4j Desktop installation](https://neo4j.com/docs/desktop/current/installation/) hoặc Deployment Center, chạy installer theo hệ điều hành.
2. Mở Desktop, tạo **local DBMS instance** và **chọn cụ thể phiên bản Neo4j** (ví dụ `2026.10.2` nếu được phân phối).
3. Ghi phiên bản và edition đã chọn. Đặt mật khẩu mạnh cho người dùng quản trị `neo4j`.
4. Chọn **Start**, đợi trạng thái sẵn sàng. Nếu thất bại, xem phần **Logs/Settings** của instance.
5. Mở công cụ **Query/Neo4j Browser** từ Desktop và chạy lệnh kiểm thử ở mục 9.

**Điều cần phân biệt:** Phiên bản **Desktop** không đồng nghĩa phiên bản **DBMS** nằm bên trong. Khi cần kiểm tra tính tương thích với ứng dụng Java, hãy ghi **Neo4j Server version** của instance. Nếu tạo hai instance cùng host, mỗi instance cần cổng riêng hoặc cơ chế quản lý kết nối phù hợp.

## 6. Cài Neo4j Server trực tiếp trên hệ điều hành

Phương án này giúp học về tiến trình, service, file cấu hình, hệ thống file và tài nguyên. Chỉ chọn khi có quyền thao tác với máy và đã xác minh OS/JVM ở mục 3.

### 6.1. Ubuntu/Debian qua kho APT chính thức

Neo4j công bố kho APT tại **debian.neo4j.com**. Theo [hướng dẫn cài .deb hiện hành](https://neo4j.com/docs/operations-manual/current/installation/linux/debian/), có thể thêm kho theo cách dùng **GPG keyring**, sau đó chọn phiên bản cụ thể.

Ví dụ lệnh trên máy Ubuntu/Debian **được Neo4j hỗ trợ**, có quyền `sudo`:

~~~bash
# 1. Tao thu muc quan ly GPG keyring
sudo mkdir -p /etc/apt/keyrings

# 2. Lay public key tu kho Neo4j va chuyen sang dinh dang keyring
wget -O - https://debian.neo4j.com/neotechnology.gpg.key |
  sudo gpg --dearmor -o /etc/apt/keyrings/neotechnology.gpg
sudo chmod a+r /etc/apt/keyrings/neotechnology.gpg

# 3. Khai bao repository
echo 'deb [signed-by=/etc/apt/keyrings/neotechnology.gpg] https://debian.neo4j.com stable latest' |
  sudo tee /etc/apt/sources.list.d/neo4j.list
sudo apt-get update

# 4. Xem cac ban co san va cai dung version cua bai
apt list -a neo4j
sudo apt-get install neo4j=1:2026.10.2
~~~

Giá trị `1:` trong `neo4j=1:2026.10.2` là **epoch** theo quy tắc phiên bản của gói Debian, không phải phần của phiên bản DBMS. Mẫu `stable latest` trong tên repository vẫn cho phép thấy bản mới hơn theo thời gian; việc pin chính xác gói giúp tránh vô tình cài bản ngoài dự định. Khi quản lý máy lâu dài, cân nhắc cả chính sách pin/hold package và quy trình nâng cấp có backup.

Gói Enterprise dùng tên `neo4j-enterprise` và có yêu cầu chấp thuận giấy phép riêng. Trên một số bản Ubuntu Server, cần bật kho `universe` để cài phụ thuộc. Nếu muốn kiểm soát thủ công hơn, có thể tải TAR cho Linux từ Deployment Center theo [Linux executable (.tar)](https://neo4j.com/docs/operations-manual/current/installation/linux/tarball/).

Sau cài đặt, Neo4j thường được quản lý bằng `systemd`:

~~~bash
# Thiet lap password lan dau TRUOC khi DBMS khoi dong lan dau
sudo -u neo4j neo4j-admin dbms set-initial-password 'REPLACE_WITH_STRONG_PASSWORD'

# Bat service va kiem tra
sudo systemctl start neo4j
sudo systemctl status neo4j
sudo journalctl -u neo4j -n 100 --no-pager
~~~

Lệnh thiết lập mật khẩu ban đầu chỉ dành cho **khởi tạo**, không phải lệnh reset mật khẩu cho database đã có tài khoản. Mật khẩu đặt trên command line có thể xuất hiện trong shell history hoặc tiến trình: trên máy dùng chung, áp dụng quy trình secret/credential của tổ chức và không đưa mật khẩu thật vào script hay Git.

> **Lưu ý quyền:** Ví dụ dùng người dùng service `neo4j` do gói APT tạo. Tùy cách cài và chính sách hệ thống, quyền chạy `neo4j-admin` có thể khác; hãy theo [hướng dẫn hệ thống dịch vụ](https://neo4j.com/docs/operations-manual/current/installation/linux/systemd/) của bản đã chọn. Trong lab mới tinh có thể để mật khẩu mặc định `neo4j` rồi đổi ngay khi đăng nhập lần đầu, nhưng không làm vậy ở môi trường mở mạng.

### 6.2. Windows bằng ZIP

1. Kiểm tra OS được hỗ trợ, Java đã cài và `java -version` trong terminal mà Neo4j sử dụng.
2. Tải **Windows Executable ZIP** phiên bản phù hợp từ Deployment Center và kiểm tra SHA-256.
3. Giải nén vào đường dẫn cố định (chẳng hạn `C:\neo4j\neo4j-2026.10.2`). Tránh đặt thư mục dữ liệu quan trọng ở nơi sẽ bị xóa khi nâng cấp.
4. Trong **Command Prompt** tại thư mục gốc bản giải nén, khởi động:

~~~bat
bin\neo4j console
~~~

5. Chờ thông báo service/connector sẵn sàng rồi mở `http://localhost:7474` và đăng nhập.

Trên Windows cũng có thể cài thành **Windows Service**, nhưng cách cấu hình service, quyền chạy và Java của service cần theo [Neo4j Windows installation](https://neo4j.com/docs/operations-manual/current/installation/windows/) cho đúng phiên bản. Nếu server chạy ổn trong console nhưng lỗi khi chạy service, ưu tiên so sánh **tài khoản service, biến môi trường Java và quyền đọc/ghi**.

### 6.3. macOS bằng TAR hoặc Homebrew

- Kiểm tra macOS/CPU và phiên bản Java trước; máy Apple Silicon dùng `arm64`, máy Intel thường là `x86_64`.
- Với gói TAR tải từ Deployment Center, giải nén và chạy lệnh `bin/neo4j console` bên trong thư mục cài (nếu đã làm theo hướng dẫn thiết lập cấu hình).
- Homebrew hỗ trợ cài **Community Edition**; theo tài liệu:

~~~bash
brew install neo4j
brew services start neo4j
brew services list
~~~

Homebrew có thể cung cấp bản mới theo thời điểm chạy lệnh. Nếu cần **đúng phiên bản** trong nhóm học/test, hãy xác minh version thực tế sau cài, kiểm tra khả năng pin version hoặc chọn gói TAR/Docker. Xem [Neo4j macOS installation](https://neo4j.com/docs/operations-manual/current/installation/osx/).

### 6.4. Thư mục và file cấu hình

| Thành phần | Vị trí thường gặp | Công dụng |
| --- | --- | --- |
| `neo4j.conf` | `<NEO4J_HOME>/conf` với ZIP/TAR; `/etc/neo4j` ở gói Linux | Connector, memory và cấu hình DBMS |
| `data` | Theo cấu hình `server.directories.data` | Lưu database; **không xóa khi muốn giữ dữ liệu** |
| `logs` | Theo `server.directories.logs` | Log khởi động, lỗi cấu hình và vận hành |
| `plugins` | Thư mục plugin theo installation | Chỉ cài plugin tương thích với phiên bản server |
| `bin` | Trong `NEO4J_HOME` hoặc `/usr/bin` tùy gói | `neo4j`, `neo4j-admin`, `cypher-shell` |

Đường dẫn thực tế thay đổi theo gói cài và OS; tra [Default file locations](https://neo4j.com/docs/operations-manual/current/configuration/file-locations/) thay vì sao chép đường dẫn từ một máy khác.

## 7. Cài bằng Docker với tag phiên bản cố định

Docker phù hợp khi cần sử dụng đúng image trong nhiều máy/CI. **Neo4j 2026.10.2 Community Edition** có tag `neo4j:2026.10.2`; Enterprise có tag tương ứng với hậu tố `-enterprise` và yêu cầu chấp thuận giấy phép. Thông tin tag nên đối chiếu [Docker introduction](https://neo4j.com/docs/operations-manual/current/docker/introduction/).

Kiểm tra Docker:

~~~bash
docker version
docker info
~~~

Kéo image chính thức và khởi động **một container thực hành local**:

~~~bash
docker pull neo4j:2026.10.2

docker run --detach --name neo4j-lab \
  --publish 127.0.0.1:7474:7474 \
  --publish 127.0.0.1:7687:7687 \
  --env NEO4J_AUTH=neo4j/REPLACE_WITH_STRONG_PASSWORD \
  --volume neo4j_lab_data:/data \
  neo4j:2026.10.2

docker ps --filter name=neo4j-lab
docker logs --tail 100 neo4j-lab
~~~

Đoạn trên dùng cú pháp **shell Linux/macOS (Bash)**; PowerShell có quy tắc nối dòng khác, hãy gõ lệnh `docker run` trên **một dòng** hoặc sử dụng Docker Compose. Thay mật khẩu placeholder trước khi chạy; password đặt qua argument là cách minh họa ngắn cho lab, không thích hợp để quản lý secret production.

Mở `http://localhost:7474` rồi đăng nhập bằng `neo4j` và mật khẩu đã đặt. Hai cổng được bind vào **127.0.0.1** để chỉ cho máy host truy cập trong bài học. Named volume `neo4j_lab_data` duy trì dữ liệu khi thay thế container.

~~~bash
# Dung container, khong xoa volume
docker stop neo4j-lab
docker start neo4j-lab

# Xem image/version container dang chay
docker inspect neo4j-lab --format '{{.Config.Image}}'
~~~

**Không dùng** `docker rm -v` hoặc xóa volume khi vẫn cần dữ liệu thực hành. Thay biến `NEO4J_AUTH` sau khi volume đã chứa user/password **không** đổi credential đang lưu trong database. Để dùng với Spring Boot chạy trong container khác, cần cấu hình chung network và địa chỉ theo tên service/container; `localhost` trong container ứng dụng không trỏ tới container Neo4j.

**Khác biệt kiểm tra JVM:** JVM của Neo4j container nằm trong image, nên `java -version` của máy host không đại diện cho JVM server. Khi cần xác minh, chạy lệnh trong container (nếu image cung cấp công cụ):

~~~bash
docker exec neo4j-lab java -version
~~~

## 8. Nếu dùng AuraDB thì “cài đặt” diễn ra ở đâu?

**Neo4j AuraDB** là dịch vụ được quản lý, nên **không tải/cài Neo4j Server hay tự cấu hình Java cho server** trên máy phát triển. Bạn tạo instance trong [Aura Console](https://console.neo4j.io/), lấy URI `neo4j+s://...`, username, password rồi chạy Cypher bằng giao diện Query hoặc ứng dụng. Yêu cầu phần cứng, phân bổ JVM và thời điểm nâng cấp Neo4j Server thuộc phạm vi dịch vụ.

Vẫn phải xác minh **phiên bản Driver**, khả năng kết nối mạng/TLS và giới hạn tài nguyên của tier AuraDB. Máy phát triển không cần cài server nhưng vẫn cần Java/JDK phù hợp nếu chạy ứng dụng Java.

## 9. Kiểm tra sau cài: làm sao biết đã đúng phiên bản?

### 9.1. Kiểm tra dịch vụ, cổng và kết nối

1. Xác nhận tiến trình/service/container ở trạng thái chạy, không restart liên tục.
2. Mở `http://localhost:7474` với bản local (hoặc endpoint HTTP thực tế); đăng nhập đúng tài khoản của **instance** vừa cài.
3. Nếu dùng Java Driver, URI local thường là `bolt://localhost:7687`, không phải URI HTTP của Browser.
4. Chạy Cypher không làm thay đổi dữ liệu:

~~~cypher
RETURN 1 + 1 AS result, datetime() AS serverTime;
~~~

Kết quả dự kiến có một dòng với `result = 2` và một giá trị thời gian. Nếu mở được Browser nhưng kết nối Cypher thất bại, cần kiểm tra **Bolt, xác thực và database thực tế**, không kết luận cài đặt đã hoàn tất.

### 9.2. Xác minh chính xác server version và edition

Khi đã đăng nhập, chạy:

~~~cypher
CALL dbms.components()
YIELD name, versions, edition
RETURN name, versions, edition;
~~~

Kết quả chứa thông tin thành phần DBMS, **danh sách phiên bản** và **edition**. Hãy ghi nhận giá trị DBMS thực tế, so sánh với phiên bản đã chọn. Điều này đáng tin cậy hơn suy đoán từ tên file tải hoặc phiên bản giao diện Desktop.

Có thể kiểm tra database đang hoạt động bằng:

~~~cypher
SHOW DATABASES;
~~~

Lệnh quản trị có thể hiển thị thông tin khác nhau theo **quyền của tài khoản và edition**; nếu không có quyền xem tất cả database, cần dùng tài khoản quản trị phù hợp cho bài thực hành quản trị.

### 9.3. Thử một property graph nhỏ

~~~cypher
MERGE (u:User {userId: 'lab-001'})
  ON CREATE SET u.name = 'An'
MERGE (p:Project {projectId: 'neo4j-lab'})
  ON CREATE SET p.title = 'Cai dat Neo4j'
MERGE (u)-[:MEMBER_OF]->(p)
RETURN u.name AS user, p.title AS project;
~~~

Đọc lại:

~~~cypher
MATCH path = (:User {userId: 'lab-001'})-[:MEMBER_OF]->(:Project {projectId: 'neo4j-lab'})
RETURN path;
~~~

Thao tác này xác minh DBMS có thể lưu **node**, **property**, **relationship** và đọc được đường đi, thay vì chỉ phản hồi truy vấn hằng số. `MERGE` giúp chạy lại mẫu mà hạn chế tạo trùng trong bài thực hành đơn giản; khi có truy cập đồng thời, dữ liệu thật vẫn cần thiết kế **uniqueness constraint**.

### 9.4. Kiểm tra tính bền vững

Với local server hoặc container **đã gắn volume**, dừng dịch vụ đúng cách, khởi động lại rồi chạy lại truy vấn `MATCH`. Nếu đồ thị vẫn còn, bạn đã xác minh dữ liệu tồn tại sau vòng đời phiên làm việc. Với AuraDB, đăng xuất/kết nối lại để kiểm tra ở mức dịch vụ.

Nếu database trống sau khi tạo lại container, kiểm tra volume được mount vào `/data`, tên volume và việc có xóa volume trước đó hay không.

## 10. Kết nối với Java Driver và Spring Data Neo4j

Khi học đến Java Driver hoặc Spring Data Neo4j, cần xác nhận **hai dải tương thích độc lập**:

| Thành phần | Yêu cầu cần kiểm tra | Ví dụ |
| --- | --- | --- |
| **Server Neo4j 2026.10.2 tự cài** | OS + JVM của server theo tài liệu 2026.10 | Chọn Java 21 hoặc Java 25 được hỗ trợ |
| **Java Driver** | JDK của **ứng dụng** và các phiên bản **Neo4j Server** mà Driver hỗ trợ | Java Driver **6.x** hỗ trợ server **4.4, 5.x, 2025.x, 2026.x** và yêu cầu Java **17+** theo tài liệu hiện hành |
| **Spring Data Neo4j** | Compatibility matrix giữa Spring Boot, Spring Data, Driver | Chọn dependency thông qua BOM của Spring Boot và đối chiếu release notes |
| **Plugin (APOC, GDS, ...)** | Phiên bản plugin có phù hợp edition và Neo4j Server | Không sao chép JAR plugin từ bản cài cũ sang bản mới |

Nguồn: [Neo4j Java Driver – Installation](https://neo4j.com/docs/java-manual/current/install/). Đây là lý do không được áp dụng yêu cầu **Java 21/25 của server** để kết luận mọi ứng dụng Java phải biên dịch bằng Java 21/25.

Khi chuyển ứng dụng từ local sang Docker hoặc AuraDB, thay **connection URI** và credential theo môi trường:

~~~properties
# application.properties (lay gia tri tu bien moi truong)
spring.neo4j.uri=${NEO4J_URI}
spring.neo4j.authentication.username=${NEO4J_USERNAME}
spring.neo4j.authentication.password=${NEO4J_PASSWORD}
~~~

Giá trị URI thường gặp: `bolt://localhost:7687` cho Java trên máy host; `bolt://neo4j:7687` cho ứng dụng cùng Docker Compose network; `neo4j+s://...` khi dùng AuraDB và TLS. Đừng lưu credential thực vào source code, repository hoặc log.

## 11. Chẩn đoán lỗi theo từng lớp

| Hiện tượng | Nguyên nhân có khả năng | Cách kiểm chứng/khắc phục |
| --- | --- | --- |
| `UnsupportedClassVersionError` hoặc JVM không khởi động | Phiên bản Java thấp hơn yêu cầu server | So `java -version` và Java mà **service** sử dụng với ma trận ở mục 2 |
| Khởi động được Desktop nhưng DBMS local không Start | DBMS/JDK của instance, quyền file, thiếu tài nguyên hoặc port xung đột | Xem **instance Logs**, kiểm tra version DBMS và cổng |
| Cài gói Linux báo thiếu dependency `daemon` | Kho `universe` trên Ubuntu Server chưa bật hoặc repository lỗi | Đọc hướng dẫn .deb, kiểm tra `apt-cache policy` và source list |
| `Connection refused` ở `localhost:7687` | DBMS chưa sẵn sàng, sai port, Bolt chưa lắng nghe | Kiểm tra log/port và URI; chờ server startup |
| `Address already in use` | Port HTTP/Bolt bị instance khác chiếm | Đổi cổng trong cấu hình hoặc dừng instance cũ |
| `Authentication failed` | Sai mật khẩu, nhầm instance hoặc volume giữ credential cũ | Xác nhận instance/credential; đổi mật khẩu bằng cơ chế quản trị phù hợp |
| Docker chạy nhưng dữ liệu mất sau khi tạo lại | Không gắn `/data` vào volume hoặc xóa volume | Kiểm tra mount và lịch sử lệnh Docker; giữ volume khi tái tạo |
| `OutOfMemoryError` hoặc container bị kill | Thiếu RAM/page cache/heap, giới hạn tài nguyên Docker | Xem log và memory limit; sizing theo workload thay vì tăng tùy ý |
| Không import được plugin | Plugin không khớp Neo4j edition/version | Tra bảng compatibility của chính plugin |
| Server mới chạy nhưng cú pháp Cypher khác tài liệu cũ | Khác bản Cypher mặc định hoặc tính năng đổi giữa release | Ghi DBMS/Cypher version; đối chiếu changelog hoặc chỉ định `CYPHER 5` khi phù hợp |
| Lỗi TLS khi kết nối AuraDB | Sai URI scheme, hostname, certificate hoặc network | Dùng nguyên `neo4j+s://` do Aura Console cấp; không tắt kiểm tra TLS |

Chẩn đoán theo thứ tự: **OS/JVM → tiến trình → log → port → URI → credential → database/edition → Cypher**. Cách này giúp không nhầm lỗi cài đặt server với lỗi Java Driver hoặc lỗi cú pháp truy vấn.

## 12. Bài thực hành: lập biên bản cài đặt có thể tái hiện

Hãy chọn **một** cách triển khai (Desktop, native hoặc Docker) và điền mẫu biên bản sau:

| Trường cần ghi | Ví dụ minh họa |
| --- | --- |
| Cách triển khai | Docker trên laptop |
| OS và kiến trúc | Ubuntu 24.04 LTS, x86_64 |
| Edition và Server version | Community, 2026.10.2 |
| Java của **server** | Runtime nằm trong Docker image; xác minh trong container |
| Java của **ứng dụng** | Java 17 (nếu có) |
| RAM và storage khả dụng | Ghi số đo thực tế ở bước preflight |
| Source và checksum | Docker official image tag/digest hoặc SHA-256 tải về |
| Browser URI | `http://localhost:7474` |
| Driver URI | `bolt://localhost:7687` |
| Database và user | `neo4j`, `neo4j` (ví dụ; không chép mật khẩu) |
| Kết quả `dbms.components()` | Ghi version, edition thực nhận |
| Kết quả Cypher | `RETURN 2` và mẫu đồ thị `User → Project` thành công |
| Kết quả restart | Dữ liệu mẫu còn tồn tại |

**Bài tập 1:** Một thành viên chạy Neo4j **2026.10.2** bằng gói TAR và chỉ có **JDK 17**. Hãy chỉ ra bước preflight không đạt và đề xuất cách sửa, không thay đổi thư mục data hiện có.

**Bài tập 2:** Một ứng dụng Spring Boot dùng **Java 17** và Java Driver 6.x kết nối Neo4j **2026.10.2**. Hãy giải thích vì sao JVM của server không nhất thiết trùng JVM ứng dụng; xác định ba thông tin kết nối tối thiểu phải có.

**Bài tập 3:** Hai người dùng cùng image Docker tag `neo4j:2026.10.2`, nhưng một người mở Browser được còn người kia báo port `7474` bị chiếm. Hãy viết ba bước chẩn đoán cụ thể, không xóa dữ liệu.

**Bài tập 4:** Bạn được yêu cầu nâng từ Neo4j 5.26 LTS lên nhánh 2026. Trước khi cài, hãy liệt kê điều cần đối chiếu: OS đã hết hỗ trợ hay chưa, JVM, edition/plugin, backup, hướng dẫn migration và sự thay đổi phiên bản Cypher mặc định.

### Checklist hoàn tất

- [ ] Đã chọn và ghi rõ phiên bản server, edition, phương thức triển khai.
- [ ] Đã đối chiếu OS, CPU, JVM, RAM, disk và yêu cầu hệ thống theo **đúng version**.
- [ ] Đã kiểm tra nguồn tải, checksum hoặc image tag/digest.
- [ ] Đã đăng nhập DBMS, xác minh `dbms.components()` và thực thi Cypher.
- [ ] Đã phân biệt URI HTTP/Browser với URI Bolt/Driver.
- [ ] Đã thử lưu và đọc lại node/relationship sau khi kết nối hoặc khởi động lại.
- [ ] Đã ghi biên bản cài đặt, không ghi mật khẩu vào tài liệu/repository.

## 13. Tài liệu chính thức để kiểm tra theo phiên bản

- [Neo4j Deployment Center](https://neo4j.com/deployment-center/) — danh sách gói, phiên bản, edition, checksum.
- [Operations Manual – System requirements](https://neo4j.com/docs/operations-manual/current/installation/requirements/) — OS, JVM và tài nguyên.
- [Operations Manual – Introduction/versioning](https://neo4j.com/docs/operations-manual/current/introduction/) — CalVer và Cypher 5/Cypher 25.
- [Neo4j Desktop – Installation](https://neo4j.com/docs/desktop/current/installation/) — cách cài Desktop và môi trường hỗ trợ.
- [Neo4j Linux – Debian packages](https://neo4j.com/docs/operations-manual/current/installation/linux/debian/) — APT và bản package cụ thể.
- [Neo4j Windows](https://neo4j.com/docs/operations-manual/current/installation/windows/) và [Neo4j macOS](https://neo4j.com/docs/operations-manual/current/installation/osx/) — khởi động native.
- [Neo4j Docker – Getting started](https://neo4j.com/docs/operations-manual/current/docker/introduction/) — image tag, port, dữ liệu và xác thực.
- [Neo4j Java Driver – Installation](https://neo4j.com/docs/java-manual/current/install/) — phiên bản Driver, JDK ứng dụng, tương thích Neo4j Server.
- [Neo4j Upgrade and Migration Guide](https://neo4j.com/docs/upgrade-migration-guide/current/) — đọc trước khi nâng phiên bản hoặc di chuyển dữ liệu.

> **Ghi nhớ khi thực hành:** **Cài đặt thành công** nghĩa là server khởi động, trả kết quả Cypher, báo **đúng phiên bản/edition** và lưu dữ liệu đúng kỳ vọng. Đây là bước nền tảng trước khi học mô hình hóa property graph, index/constraint, tối ưu và tích hợp Java.
