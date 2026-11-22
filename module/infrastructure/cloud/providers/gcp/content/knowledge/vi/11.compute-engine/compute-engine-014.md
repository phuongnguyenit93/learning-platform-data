# Thực hành triển khai dịch vụ Java trên Compute Engine

> **Chương:** Compute Engine  
> **Bài học:** Thực hành triển khai dịch vụ Java trên Compute Engine  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học cần biết **lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí**. Bài này biến các nguyên tắc đó thành một bài thực hành: triển khai một HTTP API viết bằng **Java** lên một máy ảo **Google Compute Engine**, chạy như dịch vụ hệ thống và kiểm tra qua đường truy cập quản trị an toàn.

Mục tiêu là hiểu **đường đi end-to-end** từ mã nguồn → biên dịch → VM → tiến trình Java → cổng mạng → kiểm tra sức khỏe → nhật ký → vận hành. Ví dụ sử dụng **JDK 17** và HTTP server tối giản có sẵn trong JDK để người học không phải phụ thuộc Maven hay framework. Sau khi hoàn thành, bạn có thể thay chương trình mẫu bằng **Spring Boot JAR** hoặc ứng dụng Java thực tế nhưng cần bổ sung các yêu cầu production như TLS, xác thực, kiểm soát đầu vào, autoscaling, load balancing và quan sát ứng dụng.

**Cảnh báo về chi phí và bảo mật:** các lệnh `gcloud compute instances create`, tạo VPC/subnet, firewall, service account và cài phần mềm **thay đổi tài nguyên thật**. Chỉ thực thi trên project sandbox được phê duyệt; một VM đang chạy, persistent disk, external IPv4, lưu lượng mạng, Cloud NAT và logging đều có thể phát sinh chi phí. Không chạy lệnh tạo/xóa trên production nếu chưa có quy trình thay đổi.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Mô tả trách nhiệm của người vận hành khi chọn **Compute Engine** thay vì Cloud Run hoặc GKE.
2. Tạo VPC, subnet, firewall ingress giới hạn và VM Debian trong project/zone được phép.
3. Phân biệt quyền **người quản trị VM** với **service account gắn VM** và tài khoản Linux chạy ứng dụng.
4. Biên dịch một dịch vụ Java tối giản, đóng gói JAR, cài vào thư mục dịch vụ có quyền phù hợp.
5. Dùng **systemd** để khởi động lại ứng dụng, cấu hình JVM, xem trạng thái và nhật ký bằng `journalctl`.
6. Truy cập HTTP API qua **IAP SSH port forwarding** mà không mở cổng ứng dụng ra Internet.
7. Thiết lập checklist giám sát, cập nhật phiên bản, rollback, backup và dọn dẹp tài nguyên.
8. Nhận diện những bước cần làm thêm khi chuyển từ VM đơn lẻ sang môi trường production có **managed instance group (MIG)** và load balancer.

## 2. Kiến trúc của bài thực hành

~~~mermaid
flowchart LR
    D["Người học<br/>Cloud Shell / gcloud"]
    D --> I["IAP TCP forwarding<br/>SSH 22"]
    I --> V["Compute Engine VM<br/>Debian 12 / JDK 17"]
    V --> S["systemd: orders-api"]
    S --> A["Java HTTP API<br/>127.0.0.1:8080"]
    S --> J["journald"]
    VM["VPC custom mode<br/>Subnet + firewall"] -. "Áp dụng" .-> V
    SA["Runtime service account<br/>IAM tối thiểu"] -. "Gắn với VM" .-> V
    D -. "SSH -L local port 18080" .-> A
~~~

**Các quyết định thiết kế có chủ đích:**

- **Chỉ một VM** để thấy rõ các bước cơ sở. Đây **không phải kiến trúc HA**; hỏng zone, VM, boot disk hay tiến trình có thể làm gián đoạn dịch vụ.
- API chỉ **bind tới `127.0.0.1:8080` bên trong VM**, vì thế **không lắng nghe trên IP mạng của VM**. Ta kiểm tra thông qua SSH port forwarding, không mở TCP/8080.
- VM **có external IPv4 cấp tạm** trong lab để cài gói hệ điều hành từ kho Debian dễ dàng; firewall của VPC custom mode không mở ingress Internet trừ SSH từ dải IAP được phép. **Có external IP không đồng nghĩa dịch vụ tự công khai**.
- Khi muốn VM **không có external IP**, phải thiết kế đường outbound thích hợp (ví dụ Public NAT để tải gói và artifact) và vẫn dùng IAP để quản trị.
- Runtime service account không được cấp role rộng vì dịch vụ mẫu không cần gọi Google Cloud API. Danh tính đăng nhập SSH vẫn chịu IAM và chính sách OS Login/IAP.

### 2.1. Các tham số ví dụ

| Thành phần | Giá trị minh họa | Ý nghĩa |
|---|---|---|
| Project | `PROJECT_ID` | Project sandbox đã có billing và quyền phù hợp |
| Region | `asia-southeast1` | Singapore; lựa chọn vì ví dụ, không bắt buộc |
| Zone | `asia-southeast1-a` | Một zone trong region ví dụ |
| VPC | `java-lab-vpc` | Mạng custom mode |
| Subnet | `java-lab-subnet` | `10.60.0.0/24` |
| Firewall | `java-lab-allow-iap-ssh` | Chỉ nguồn IAP TCP forwarding tới TCP/22 trên VM có target tag |
| VM | `java-orders-lab` | Debian 12, `e2-standard-2` minh họa |
| Runtime service account | `java-lab-runtime@PROJECT_ID.iam.gserviceaccount.com` | Danh tính workload, chưa cấp IAM role cho ứng dụng |
| Linux service user | `javaorders` | Không dùng root để chạy ứng dụng |
| Application | `/opt/java-orders/orders-api.jar` | JAR triển khai |
| API listen address | `127.0.0.1:8080` | Chỉ cổng loopback trong VM |
| Port forwarding | `localhost:18080 → VM:127.0.0.1:8080` | Người học truy cập bằng SSH qua IAP |

**Giới hạn học thuật:** hướng dẫn không giả định project đã có quyền tạo VPC hoặc SSH. Nếu chỉ có quyền xem, bạn vẫn có thể hoàn thành các phần thiết kế/đọc lệnh và mô tả kết quả mong đợi mà không thực thi.

## 3. Chuẩn bị trước khi tạo tài nguyên

Bạn cần:

- Tài khoản Google được cấp quyền trên **project sandbox** có liên kết billing account.
- **Google Cloud CLI (`gcloud`)** trong Cloud Shell hoặc máy đã được xác thực.
- Quyền tạo VM, VPC, subnet, firewall và service account **chỉ khi làm lab thật**; quyền sử dụng service account được gắn vào VM.
- Quyền **IAP-secured Tunnel User** (`roles/iap.tunnelResourceAccessor`) và quyền **OS Login** thích hợp (`roles/compute.osLogin`, hoặc role admin OS Login khi thật sự cần), cùng quyền xem thông tin VM theo yêu cầu.
- Quy tắc tổ chức cho phép VM có external IP tạm trong sandbox. Nếu tổ chức chặn external IP, dùng phương án **không external IP + outbound đã thiết kế** thay vì tìm cách bypass policy.
- Kiến thức Linux cơ bản: SSH, `sudo`, `systemctl`, `journalctl`, `curl`, `ss`.

Trước khi tạo, kiểm tra:

~~~bash
gcloud auth list
gcloud config get-value project
gcloud projects describe PROJECT_ID \
  --format="yaml(projectId,name,projectNumber)"
gcloud compute zones describe asia-southeast1-a \
  --project=PROJECT_ID \
  --format="yaml(name,region,status)"
~~~

Nếu `gcloud config get-value project` trả về project khác, hãy **truyền `--project=PROJECT_ID` rõ trong mọi lệnh ghi tài nguyên**, như các ví dụ bên dưới. Không phụ thuộc duy nhất vào project mặc định trong Cloud Shell.

### 3.1. Ước tính chi phí và tránh nhầm sản phẩm miễn phí

Một VM `e2-standard-2` và persistent disk **không mặc định nằm trong Free Tier**. External IPv4 cũng có thể phát sinh phí kể cả khi được gắn với VM; các dịch vụ bổ sung như logging và egress có quy tắc giá riêng.

Trước bài thực hành, mở **Billing → Budgets & alerts** (nếu được cấp quyền) để xem budget, tạo cảnh báo phù hợp và ghi người nhận. **Budget alert thông thường không phải công tắc tự dừng chi tiêu**. Ghi giờ bắt đầu/kết thúc, danh sách tài nguyên dự định xóa và người chịu trách nhiệm.

### 3.2. Chuẩn hóa quyền và cấu hình nguồn

Dùng các giá trị placeholder đúng định dạng và thay bằng tên thật trước khi thực hiện. Các tên `PROJECT_ID`, `ZONE`, `VM_NAME`, `SUBNET_NAME` trong bài không phải tài nguyên đã tồn tại.

**Không copy private key, API token, mật khẩu database hoặc service account JSON vào startup script, command history hay repository.** Ứng dụng Java mẫu không cần secret; khi chuyển sang sản xuất phải dùng Secret Manager/managed identity theo thiết kế.

## 4. Bước 1 — Tạo mạng riêng cho bài lab

Một **custom mode VPC** giúp người học xác định rõ subnet, firewall và ranh giới network. Không dùng default VPC có sẵn nếu không biết các rule mặc định, vì một số default firewall rules có thể mở ingress SSH từ nguồn rất rộng.

Các lệnh sau **có tác động** lên project:

~~~bash
# Tạo custom mode VPC.
gcloud compute networks create java-lab-vpc \
  --project=PROJECT_ID \
  --subnet-mode=custom

# Tạo subnet regional có CIDR riêng.
gcloud compute networks subnets create java-lab-subnet \
  --project=PROJECT_ID \
  --network=java-lab-vpc \
  --region=asia-southeast1 \
  --range=10.60.0.0/24

# Chỉ cho phép SSH từ hệ thống IAP TCP forwarding đến VM gắn tag lab.
gcloud compute firewall-rules create java-lab-allow-iap-ssh \
  --project=PROJECT_ID \
  --network=java-lab-vpc \
  --direction=INGRESS \
  --priority=1000 \
  --action=ALLOW \
  --rules=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags=java-lab-ssh
~~~

**Giải thích:**

- VPC là tài nguyên **global**, subnet là tài nguyên **regional**.
- Dải `10.60.0.0/24` là ví dụ; kiểm tra **overlap** với VPC, peering hoặc on-premises nếu dùng chung tài nguyên.
- Nguồn `35.235.240.0/20` là dải IPv4 phục vụ **IAP TCP forwarding** cho các tình huống SSH phù hợp; chỉ mở TCP/22 và chỉ nhắm VM có tag `java-lab-ssh`.
- Không có rule nào trong ví dụ mở TCP/8080, TCP/80 hoặc TCP/443 tới VM. Firewall mặc định của custom VPC không tự cho phép ingress tùy ý.
- Các **hierarchical firewall policies** hoặc **network firewall policies** ở organization/folder/VPC có thể tiếp tục hạn chế lưu lượng; rule trên không vượt qua deny từ lớp ưu tiên cao hơn.

### 4.1. Vì sao lab cần external IP dù không mở dịch vụ ra Internet?

Mục tiêu của external IP trong bài là **outbound** tới kho Debian khi cài JDK. Cách học có chi phí và bảo mật tốt hơn trong tổ chức đã có nền tảng mạng là **VM không external IP**, sử dụng **Public NAT** cho outbound cần thiết và IAP cho SSH. Nhưng không được gọi `--no-address` rồi giả định `apt-get update` vẫn truy cập Internet: **Private Google Access không thay thế NAT cho mọi kho phần mềm công khai**.

Khi kiểm tra mạng, đừng đánh đồng ba điều:

1. VM có external IPv4.
2. VPC có route/default route tới Internet và egress được cho phép.
3. Có ingress allow rule tới port của ứng dụng.

Chỉ điều (1) không đủ để người lạ từ Internet gọi được API; điều (3) mới là một phần của quyết định cho truy cập từ ngoài, và vẫn còn TLS/ứng dụng/OS firewall.

## 5. Bước 2 — Tạo runtime service account và VM

### 5.1. Tách danh tính người quản trị với danh tính ứng dụng

**Người học** đăng nhập Cloud Shell bằng managed user và quyền tạo tài nguyên được cấp. **VM** gắn một Google service account riêng. Tiến trình Java **không** nên chạy bằng tài khoản root của Linux.

Ba lớp danh tính:

| Danh tính | Dùng cho | Quyền nên cấp |
|---|---|---|
| Managed user / Google account | Triển khai, SSH và bảo trì VM | Role trên sandbox và IAP/OS Login cần thiết |
| Google Cloud service account của VM | Ứng dụng gọi Google APIs khi cần | Chỉ role cụ thể theo tài nguyên; demo chưa cần |
| Linux user `javaorders` | Chạy process Java trong hệ điều hành | Chỉ đọc JAR và những thư mục cần thiết |

Tạo service account dành riêng cho lab:

~~~bash
gcloud iam service-accounts create java-lab-runtime \
  --project=PROJECT_ID \
  --display-name="Java Compute Engine lab runtime"
~~~

Nếu tài khoản này chỉ phục vụ HTTP API mẫu và không gọi dịch vụ Google Cloud, **không cấp Editor/Owner**. Khi ứng dụng thực sự cần Cloud Storage/Pub/Sub, cấp đúng quyền nhỏ nhất trên bucket/topic tương ứng rồi kiểm tra quyền bằng IAM Policy Troubleshooter.

### 5.2. Tạo máy ảo

~~~bash
gcloud compute instances create java-orders-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --machine-type=e2-standard-2 \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=20GB \
  --boot-disk-type=pd-balanced \
  --subnet=java-lab-subnet \
  --tags=java-lab-ssh \
  --labels=env=lab,app=orders-api \
  --metadata=enable-oslogin=TRUE \
  --service-account=java-lab-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --scopes=cloud-platform
~~~

**Lý do của một số cờ:**

- `e2-standard-2` đủ dư địa cho JDK và API thử, nhưng là lựa chọn minh họa, không phải sizing production.
- `debian-12` là image family trong project `debian-cloud`; image thực tế được chọn theo phiên bản tại thời điểm tạo.
- `--metadata=enable-oslogin=TRUE` bật luồng quản lý SSH bằng **OS Login** cho VM nếu tổ chức cho phép.
- `--service-account=...` chọn **identity khi runtime**; việc gắn service account có thể yêu cầu quyền **Service Account User** (`iam.serviceAccounts.actAs`).
- `--scopes=cloud-platform` cho phép phạm vi OAuth rộng ở lớp access scopes, nhưng **không tự cấp IAM role** cho service account. Quyền API vẫn phải được cấp bằng IAM và các chính sách liên quan. Khi thiết kế môi trường mới, nên quản lý quyền qua IAM tối thiểu.
- Không truyền `--no-address` trong luồng cơ bản, nên VM có thể nhận external IPv4 tạm theo cấu hình network và chính sách project. **Không tạo ingress allow** tới ứng dụng.

**Nếu lệnh thất bại:** đọc lỗi cụ thể về IAM, API chưa bật, billing, quota, zone capacity, image hoặc Organization Policy. Không giải quyết bằng cách cấp `roles/owner` tràn lan.

### 5.3. Readback VM và mạng

~~~bash
gcloud compute instances describe java-orders-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --format="yaml(name,status,machineType,networkInterfaces,serviceAccounts,tags,metadata)"

gcloud compute firewall-rules describe java-lab-allow-iap-ssh \
  --project=PROJECT_ID
~~~

Ghi lại VM status `RUNNING`, internal IP, network, tag và runtime service account. Kiểm tra không có firewall rule khác trên organization/folder/VPC mở ứng dụng ngoài ý muốn.

## 6. Bước 3 — Đăng nhập vào VM qua IAP

Trong Cloud Shell, chạy:

~~~bash
gcloud compute ssh java-orders-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --tunnel-through-iap
~~~

`--tunnel-through-iap` buộc dùng IAP TCP forwarding cho SSH. Đường này có thể hoạt động cả khi VM không có external IP; cần role IAP/OS Login, firewall tương ứng và các cấu hình SSH bình thường.

Sau khi SSH vào Debian:

~~~bash
whoami
hostname
cat /etc/os-release
java -version || true
sudo systemctl status ssh --no-pager
ip -br address
~~~

Các lệnh quan sát giúp xác định bạn thật sự đang ở VM Debian. `java -version` có thể báo `command not found` trước khi cài JDK; điều đó được mong đợi.

### 6.1. Nếu SSH thất bại

| Hiện tượng | Khả năng cần kiểm tra | Hướng xử lý |
|---|---|---|
| `PERMISSION_DENIED` khi tạo IAP tunnel | Thiếu `roles/iap.tunnelResourceAccessor` hoặc policy chặn | Kiểm tra danh tính và IAM ở đúng VM/IAP resource |
| OS Login từ chối | Thiếu `roles/compute.osLogin`, role không phù hợp hoặc policy tổ chức | Kiểm tra OS Login settings và quyền tương ứng |
| SSH timeout | Firewall IAP TCP/22, VM không chạy, route/OS SSH server lỗi | Kiểm tra rule target tag và trạng thái VM |
| `NOT_FOUND` | Sai project/zone hoặc thiếu quyền xem | `instances describe` và đối chiếu project selector |
| Không thể bật external IP | Chính sách tổ chức | Dùng thiết kế VM private + Public NAT đúng quy trình, không bypass |
| Đăng nhập đúng VM nhưng không thấy code | Đang ở máy khác hoặc chưa triển khai | Kiểm tra hostname và bước copy/build |

**IAP chỉ điều khiển đường kết nối mạng**; nó không thay OS Login, xác thực SSH hoặc IAM cho các hoạt động trên VM.

## 7. Bước 4 — Cài Java và tạo API mẫu

Trong phiên **SSH trên VM**, cập nhật danh sách gói và cài JDK 17:

~~~bash
sudo apt-get update
sudo apt-get install -y openjdk-17-jdk-headless curl
java -version
javac -version
~~~

Debian 12 cung cấp OpenJDK 17 trong môi trường gói thông thường. Nếu doanh nghiệp dùng mirror riêng hoặc image mới có cấu hình khác, hãy kiểm tra tên package tương ứng; không tải JDK từ nguồn không đáng tin cậy chỉ vì `apt` báo lỗi.

### 7.1. Viết dịch vụ Java không cần framework

Tạo file `OrdersApi.java` trong thư mục làm việc của user SSH:

~~~bash
cat > OrdersApi.java <<'EOF'
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.Executors;

public final class OrdersApi {
    public static void main(String[] args) throws IOException {
        String host = System.getenv().getOrDefault("BIND_HOST", "127.0.0.1");
        int port = Integer.parseInt(System.getenv().getOrDefault("PORT", "8080"));

        HttpServer server = HttpServer.create(
            new InetSocketAddress(host, port), 64);

        server.createContext("/healthz", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())) {
                reply(exchange, 405, "text/plain", "Method Not Allowed\n");
                return;
            }
            reply(exchange, 200, "text/plain", "OK\n");
        });

        server.createContext("/api/orders", exchange -> {
            if (!"GET".equals(exchange.getRequestMethod())
                    || !"/api/orders".equals(exchange.getRequestURI().getPath())) {
                reply(exchange, 405, "text/plain", "Method Not Allowed\n");
                return;
            }
            reply(exchange, 200, "application/json",
                  "{\"orders\":[],\"source\":\"compute-engine\"}\n");
        });

        server.setExecutor(Executors.newFixedThreadPool(4));
        System.out.println("Orders API listening on " + host + ":" + port);
        server.start();
    }

    private static void reply(HttpExchange exchange, int status,
                              String contentType, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", contentType + "; charset=utf-8");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }
}
EOF
~~~

Đây là **API mô phỏng**: `GET /healthz` trả `200 OK` và `GET /api/orders` trả JSON với danh sách rỗng. Không có database và không lưu thông tin khách hàng. Khi cần API thật, ứng dụng Spring Boot có thể kết nối Cloud SQL, Cloud Storage hay Pub/Sub bằng runtime service account và quyền phù hợp.

### 7.2. Biên dịch và đóng gói

~~~bash
javac --add-modules jdk.httpserver OrdersApi.java

jar --create \
  --file orders-api.jar \
  --main-class=OrdersApi \
  OrdersApi.class

ls -lh OrdersApi.class orders-api.jar
~~~

Module `jdk.httpserver` là HTTP server tối giản thuộc JDK, thích hợp cho **bài học** chứ **không** phải lựa chọn đầy đủ cho API production. Lệnh `jar --main-class` tạo JAR có điểm khởi chạy.

### 7.3. Chạy thử trước khi cấu hình systemd

~~~bash
java --add-modules jdk.httpserver \
  -Xms64m -Xmx256m \
  -jar orders-api.jar
~~~

Trong một **phiên SSH thứ hai trên chính VM**, dùng:

~~~bash
curl --fail --show-error http://127.0.0.1:8080/healthz
curl --fail --show-error http://127.0.0.1:8080/api/orders
~~~

Kỳ vọng:

~~~text
OK
{"orders":[],"source":"compute-engine"}
~~~

Dừng lần chạy thử bằng `Ctrl+C` trong terminal Java trước khi bật systemd; nếu vẫn chiếm cổng 8080, dịch vụ systemd sẽ lỗi `Address already in use`.

## 8. Bước 5 — Chạy Java như một dịch vụ Linux bằng systemd

Một cửa sổ terminal được đóng hoặc người dùng SSH bị ngắt không nên khiến ứng dụng dừng. `systemd` có thể quản lý tiến trình Java độc lập, tự khởi động sau reboot và ghi stdout/stderr vào journal.

### 8.1. Tạo user Linux chỉ dùng chạy ứng dụng

~~~bash
sudo useradd \
  --system \
  --home-dir /opt/java-orders \
  --shell /usr/sbin/nologin \
  javaorders

sudo install -d \
  -o javaorders -g javaorders -m 0750 \
  /opt/java-orders

sudo install \
  -o javaorders -g javaorders -m 0640 \
  orders-api.jar /opt/java-orders/orders-api.jar
~~~

Nếu user `javaorders` đã tồn tại khi làm lại lab, không chạy `useradd` lần nữa; xác minh `id javaorders` và quyền thư mục thay vì tạo user trùng. Quyền file `0640` cho phép service user đọc JAR; chỉ người có quyền quản trị mới được thay artifact.

**Không chạy ứng dụng bằng root** chỉ để tránh lỗi permission. Khi một ứng dụng thật cần ghi dữ liệu, tạo thư mục riêng phù hợp như `/var/lib/orders-api` và chỉ cấp quyền ghi tối thiểu.

### 8.2. Tạo unit file

~~~bash
sudo tee /etc/systemd/system/orders-api.service > /dev/null <<'EOF'
[Unit]
Description=Orders API demo on Compute Engine
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=javaorders
Group=javaorders
WorkingDirectory=/opt/java-orders
Environment=PORT=8080
Environment=BIND_HOST=127.0.0.1
ExecStart=/usr/bin/java --add-modules jdk.httpserver -Xms64m -Xmx256m -jar /opt/java-orders/orders-api.jar
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now orders-api
~~~

**Giải thích các cấu hình quan trọng:**

- `User=javaorders` và `Group=javaorders`: tiến trình chạy không có đặc quyền root.
- `ExecStart`: gọi Java bằng đường dẫn tuyệt đối, JAR đã được cài ở `/opt`.
- `-Xms64m -Xmx256m`: JVM heap chỉ để minh họa, không đại diện sizing cho Spring Boot hay workload thật. RAM của OS, heap, metaspace và native allocations vẫn cần giới hạn/quan sát riêng.
- `Environment=BIND_HOST=127.0.0.1`: dịch vụ chỉ mở loopback. Cần thay đổi kiến trúc trước khi đưa sau load balancer.
- `Restart=on-failure`: khởi động lại nếu ứng dụng thoát với lỗi; không thay cho health check chủ động, readiness/liveness hay failover.
- `NoNewPrivileges`, `ProtectHome`, `ProtectSystem` và `PrivateTmp`: tăng cô lập systemd ở mức cơ bản; ứng dụng thật có thể cần điều chỉnh các quyền ghi và syscall cần thiết.

Nếu service không khởi động, xem log thay vì đổi `User=root`:

~~~bash
sudo systemctl status orders-api --no-pager
sudo journalctl -u orders-api -n 100 --no-pager
sudo ss -lntp | grep ':8080' || true
~~~

### 8.3. Kiểm tra sau reboot

~~~bash
sudo systemctl is-enabled orders-api
sudo systemctl is-active orders-api
curl --fail --show-error http://127.0.0.1:8080/healthz
~~~

Một ứng dụng được `systemctl enable` có thể tự chạy sau reboot, nhưng **chưa có HA** và **reboot vẫn làm gián đoạn kết nối**. Nếu doanh nghiệp yêu cầu không gián đoạn, dùng nhiều instance, load balancing và quy trình rolling deployment.

## 9. Bước 6 — Kiểm tra từ Cloud Shell qua IAP port forwarding

Đóng phiên SSH thao tác trên VM sau khi xác nhận systemd đang chạy, rồi mở **một terminal Cloud Shell** để tạo SSH port forwarding:

~~~bash
gcloud compute ssh java-orders-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a \
  --tunnel-through-iap \
  -- -N -L 18080:127.0.0.1:8080
~~~

Lệnh tạo ánh xạ **Cloud Shell localhost:18080 → VM localhost:8080** thông qua SSH trên IAP. Phiên có thể giữ terminal ở trạng thái hoạt động mà không in prompt; đó là hành vi dự kiến với `-N`. Giữ terminal này mở khi kiểm tra.

Mở **terminal Cloud Shell thứ hai** và chạy:

~~~bash
curl --fail --show-error http://127.0.0.1:18080/healthz
curl --fail --show-error http://127.0.0.1:18080/api/orders
~~~

Kết quả mong đợi:

~~~text
OK
{"orders":[],"source":"compute-engine"}
~~~

**Tại sao không mở TCP/8080 ra Internet?**

1. Đây là API demo chưa có TLS, authorization, rate limiting hoặc kiểm tra dữ liệu đầu vào đầy đủ.
2. Loopback bind cho phép thử chức năng mà không công khai dịch vụ.
3. IAP kiểm soát **SSH transport** và IAM; không biến API HTTP demo thành API công khai an toàn.
4. Để phục vụ người dùng thật, cần ingress phù hợp qua load balancer, TLS, nhận dạng người dùng và chính sách ứng dụng.

Để dừng port forwarding, dùng `Ctrl+C` ở terminal chạy SSH tunnel. Dừng tunnel SSH **không dừng** `orders-api` đang chạy dưới systemd.

### 9.1. Phân biệt ba kiểu kiểm tra

| Kiểu thử | Kiểm tra điều gì | Điều không chứng minh |
|---|---|---|
| `curl 127.0.0.1:8080` **trên VM** | JVM đã bind, HTTP handler trả lời cục bộ | Người ngoài VPC có truy cập được không |
| `curl 127.0.0.1:18080` **từ Cloud Shell qua SSH -L** | IAP + SSH + port forward + JVM hoạt động | Cổng 8080 đã được mở trên VPC |
| Gọi HTTPS qua production load balancer | End-to-end từ client tới frontend, backend và app | Mọi zone/instance đều healthy nếu chỉ thử một lần |

**Tránh nhầm:** port forwarding kết nối qua SSH nên **không cần** mở ingress TCP/8080 ở VPC firewall. Chỉ cần đường SSH/IAP tới VM và tiến trình nghe trên loopback trong VM.

## 10. Bước 7 — Quan sát trạng thái, log và tài nguyên

### 10.1. Kiểm tra dịch vụ ở Linux

~~~bash
sudo systemctl status orders-api --no-pager
sudo journalctl -u orders-api --since "30 minutes ago" --no-pager
sudo journalctl -u orders-api -f
ps -eo pid,user,%cpu,%mem,cmd | grep '[j]ava'
free -h
df -h
sudo ss -lntp | grep ':8080' || true
~~~

- `journalctl -u` xem log stdout/stderr của tiến trình do systemd quản lý.
- `-f` theo dõi log trực tiếp; dùng `Ctrl+C` để dừng xem log, **không dừng service**.
- `free -h` quan sát RAM host; `df -h` quan sát dung lượng filesystem. Java heap chỉ là một phần của memory footprint.
- `ss` cho thấy ứng dụng đang lắng nghe địa chỉ và port nào. Với bài này kỳ vọng `127.0.0.1:8080` chứ không phải `0.0.0.0:8080`.

### 10.2. Cloud Monitoring và Cloud Logging

Google Cloud cung cấp các metric VM cơ bản. Để lấy thông tin chi tiết hơn về **memory, disk, process** và thu thập log hệ điều hành, doanh nghiệp có thể triển khai **Ops Agent** theo hướng dẫn chính thức.

Một quy trình an toàn:

1. Xác định project/VM và yêu cầu tổ chức cho phép cài Ops Agent.
2. Kiểm tra runtime service account có quyền ghi log/metric cần thiết, chẳng hạn `roles/logging.logWriter` và `roles/monitoring.metricWriter` theo phạm vi phù hợp.
3. Cài Ops Agent đúng image/OS và cấu hình chính sách log/metric cho workload.
4. Kiểm tra log từ `orders-api.service` đã được thu thập hay chưa; đừng mặc định tất cả `journald` đều được gửi về Cloud Logging nếu chưa cấu hình.
5. Tạo dashboard/alert theo availability, CPU, memory, disk, lỗi khởi động và response time của ứng dụng theo dữ liệu thực tế.

**Không gán `Editor` cho VM service account để sửa lỗi gửi log**. Xác định chính xác permission đang thiếu, role tương ứng và cập nhật qua người quản lý IAM.

### 10.3. Chỉ số cần theo dõi khi chuyển production

| Nhóm | Metric / tín hiệu | Rủi ro cần phát hiện |
|---|---|---|
| Máy ảo | CPU, memory pressure, disk utilization | VM thiếu tài nguyên hoặc disk đầy |
| JVM | Heap, GC pause, thread pool, file descriptors | OOM, latency cao hoặc leak |
| HTTP API | RPS, p95/p99 latency, 4xx/5xx, health/readiness | Người dùng bị lỗi dù VM vẫn RUNNING |
| Hệ điều hành | Reboot, package updates, process restarts | Không có tiến trình phục vụ |
| Mạng | Port binding, firewall, VPC route, NAT/egress | Có IP nhưng không kết nối được |
| Dữ liệu | Cloud SQL connections, timeout, backup status | Lỗi DB làm API thất bại |
| Bảo mật | Failed SSH, IAM changes, patch status, secrets | Truy cập trái phép, lộ thông tin |
| Chi phí | VM hours, disk, external IP, network egress/logging | Vượt ngân sách thử nghiệm |

API demo chỉ có `/healthz` đơn giản; trong ứng dụng thật, **liveness** và **readiness** nên có ý nghĩa khác nhau. Readiness có thể kiểm tra các phụ thuộc thiết yếu một cách an toàn, nhưng không nên tạo lệnh kiểm tra quá nặng gây thêm tải hoặc lộ thông tin nhạy cảm.

## 11. Bước 8 — Quy trình phát hành phiên bản và rollback

Một service chạy được một lần vẫn chưa đủ để quản trị nhiều lần deploy. Cần có **artifact version**, truy vết người phát hành và rollback đã được chuẩn bị.

### 11.1. Cách cập nhật JAR trên VM demo

Sau khi build và kiểm tra JAR mới trong môi trường phát triển:

1. Kiểm tra phiên bản nguồn, Java target version và checksum của artifact.
2. Chuyển artifact vào VM qua luồng được phê duyệt như `gcloud compute scp ... --tunnel-through-iap` hoặc tải từ Artifact Registry/Cloud Storage bằng runtime identity phù hợp.
3. Lưu bản JAR cũ để rollback.
4. Dừng service theo change window, cài JAR mới với quyền `javaorders`, khởi động lại.
5. Xác minh `/healthz` và `/api/orders`, xem `journalctl` và metric.
6. Nếu lỗi, khôi phục bản cũ và kiểm tra lại.

Ví dụ **thao tác ngay trong VM**, giả sử artifact mới đã được chuyển đến `$HOME/orders-api-new.jar`:

~~~bash
# Sao lưu artifact hiện hành để rollback trên chính VM lab.
sudo cp -a /opt/java-orders/orders-api.jar \
  /opt/java-orders/orders-api.jar.backup

# Cài artifact mới với quyền của service user.
sudo install \
  -o javaorders -g javaorders -m 0640 \
  "$HOME/orders-api-new.jar" \
  /opt/java-orders/orders-api.jar

sudo systemctl restart orders-api
sudo systemctl is-active orders-api
curl --fail --show-error http://127.0.0.1:8080/healthz
~~~

Nếu health check thất bại:

~~~bash
sudo systemctl stop orders-api
sudo cp -a /opt/java-orders/orders-api.jar.backup \
  /opt/java-orders/orders-api.jar
sudo systemctl start orders-api
sudo systemctl status orders-api --no-pager
~~~

Đây là rollback file trên **một VM**, **không phải** triển khai zero-downtime. Một bản JAR cũ có thể không tương thích với thay đổi schema/database mới; vì thế production cần xem xét khả năng rollback **ứng dụng và dữ liệu** cùng nhau.

### 11.2. Vì sao cần CI/CD và artifact repository?

Một pipeline production thường có các bước:

~~~mermaid
flowchart LR
    G["Git commit / Pull request"]
    G --> CI["Build + unit tests + SAST/dependency checks"]
    CI --> AR["Versioned JAR/image<br/>Artifact Registry"]
    AR --> CD["Triển khai thử staging"]
    CD --> AP["Approval + policy checks"]
    AP --> R["MIG rolling update / canary"]
    R --> OBS["Health checks + monitoring"]
    OBS --> RB["Tiếp tục hoặc rollback"]
~~~

Bài lab build ngay trên VM để học được cơ chế. Môi trường production nên **build một lần, triển khai cùng artifact đã kiểm thử nhiều nơi**, dùng service identity cho CI/CD, hạn chế quyền `ssh` và lưu dấu vết bản phát hành.

## 12. Khi đưa Java API ra ngoài: từ một VM đến kiến trúc production

Không nên công khai trực tiếp HTTP server tối giản qua `--address=0.0.0.0` rồi mở `0.0.0.0/0:8080`. Có nhiều giải pháp khác nhau:

### 12.1. External Application Load Balancer + MIG

~~~mermaid
flowchart TB
    U["Internet clients"]
    U --> DNS["Cloud DNS: api.example.com"]
    DNS --> HTTPS["External Application Load Balancer<br/>HTTPS + certificate"]
    HTTPS --> MIG["Regional Managed Instance Group"]
    MIG --> VM1["VM Java #1<br/>zone a"]
    MIG --> VM2["VM Java #2<br/>zone b"]
    VM1 --> SQL["Cloud SQL private connectivity"]
    VM2 --> SQL
    VM1 --> PUB["Pub/Sub / Cloud Storage"]
    VM2 --> PUB
    MON["Cloud Monitoring / Cloud Logging"] -. "Telemetry" .-> MIG
~~~

**MIG** dùng **instance template** xác định machine type, image, startup script hoặc cách lấy artifact, service account và network. Load balancer dùng health checks để chỉ gửi traffic tới backend phù hợp; có thể kết hợp autoscaling/rolling update.

Khi chuyển từ demo sang MIG/load balancer phải thay đổi có chủ đích:

- Ứng dụng phải lắng nghe trên **interface được backend dùng**, không chỉ `127.0.0.1`, hoặc đi qua reverse proxy/sidecar phù hợp. **Chỉ thay `BIND_HOST` khi các biện pháp ingress đã sẵn sàng.**
- Firewall backend chỉ cho phép **nguồn load balancer/proxy và health checks** phù hợp **loại load balancer đang dùng**; không mở toàn Internet.
- Thiết lập **TLS** tại frontend và phương án TLS end-to-end nếu chính sách yêu cầu.
- Sử dụng **regional MIG** nhiều zone để giảm rủi ro lỗi một zone; đánh giá capacity và autoscaler.
- Ứng dụng nên **stateless**, lưu dữ liệu bền vững trên Cloud SQL/Cloud Storage hoặc dịch vụ tương đương.
- Tách **liveness** và **readiness**, có lifecycle shutdown để không mất request khi rolling update.
- Dùng IAM, Secret Manager, database auth, backups và log đúng chuẩn production.

### 12.2. Có nên chọn Cloud Run hoặc GKE thay VM?

| Lựa chọn | Phù hợp khi | Trách nhiệm vận hành |
|---|---|---|
| **Compute Engine VM** | Cần tùy biến OS/JVM sâu, legacy software, kiểm soát process/disk/network cụ thể | Patch OS/JDK, bảo mật host, HA, scale, deploy, logging |
| **Compute Engine + MIG** | Muốn vận hành VM nhưng cần HA, autoscaling và rolling deployments | Vẫn quản lý images/templates/OS cùng với MIG/LB |
| **Cloud Run** | HTTP API/container stateless, cần giảm quản trị server và scale theo request | Quản trị container, IAM/ingress, dependencies, observability |
| **GKE** | Nhiều service/container có nhu cầu Kubernetes, network/policy/orchestration | Cluster/workload config, RBAC, network, images, SLO |

Nếu Java REST API đã đóng gói container, ít phụ thuộc OS và có traffic biến động, **Cloud Run** có thể giảm đáng kể phần việc quản trị VM. Nếu cần driver riêng, chạy tác vụ lâu dài hoặc kiểm soát host chi tiết, Compute Engine vẫn hữu ích. Quyết định phải dựa trên workload, SLO, bảo mật và tổng chi phí.

## 13. Quản lý secrets, IAM, VPC và bản vá bảo mật

### 13.1. Phân tách các lớp quyền

| Lớp | Quyền nên kiểm soát | Ví dụ |
|---|---|---|
| Cloud IAM | Ai tạo VM/đổi firewall/SSH/xem log | Nhóm dev không cần `roles/owner` |
| IAP/OS Login | Ai vào VM theo thời gian và chính sách | Role IAP + role OS Login thích hợp |
| Linux | Ai được đọc/ghi JAR, cấu hình và log | `javaorders` không phải root |
| Runtime service account | Workload được gọi Cloud Storage/Pub/Sub gì | Bucket/topic-specific roles |
| Network | VM được liên lạc với nguồn/đích/port nào | Custom VPC, firewall, Cloud NAT |
| Ứng dụng | API user có được xem/sửa đơn hàng không | OAuth/JWT, authorization trong Java app |

### 13.2. Không dùng secrets trong file service unit công khai

Trong lab, service chỉ có `PORT` và `BIND_HOST`. Ứng dụng sản xuất có thể cần mật khẩu database, API key hoặc token. Tránh đưa chúng vào:

- `ExecStart` hoặc `Environment=DB_PASSWORD=...` trong unit file dễ được đọc/backup sai phạm vi.
- Source code, file JAR, Git, startup script hoặc log.
- Service account JSON key dài hạn nếu có thể dùng identity gắn VM.

Nên dùng **Secret Manager** với service account runtime và role truy cập đúng secret; đặt cơ chế cache, rotation và xử lý trường hợp Secret Manager tạm không truy cập được theo nhu cầu ứng dụng.

### 13.3. Bảo vệ Compute Engine VM

- **OS Login/IAP:** giảm nhu cầu quản lý SSH key và mở SSH công khai.
- **Shielded VM:** xem cấu hình Secure Boot/vTPM/integrity monitoring khi image và ứng dụng hỗ trợ.
- **OS patching:** có quy trình cập nhật Debian/JDK, thử ở staging, reboot/rollout theo thời gian bảo trì.
- **Disk encryption/backups:** Compute Engine có cơ chế mã hóa dữ liệu; yêu cầu CMEK hoặc chính sách riêng cần kiểm tra với tổ chức.
- **Least privilege:** service account không được cấp Owner/Editor chỉ vì cần lấy artifact.
- **Network firewall:** hạn chế ingress, quản lý egress, hiểu hierarchical/network policies ở tổ chức.
- **Audit:** lưu thay đổi IAM/firewall/VM và phiên deploy theo retention được phê duyệt.

## 14. Vấn đề thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `gcloud compute instances create` lỗi quyền | Thiếu IAM permission, `iam.serviceAccounts.actAs` hoặc policy tổ chức | Đọc lỗi cụ thể, xác định scope và yêu cầu role nhỏ nhất |
| VM không có outbound để `apt-get update` | Dùng `--no-address` nhưng chưa có NAT/egress | Kiểm tra Public NAT, default route, egress firewall và DNS |
| SSH IAP `PERMISSION_DENIED` | Thiếu IAP/OS Login roles hoặc policy chặn | Đối chiếu IAM của người truy cập |
| SSH IAP timeout | Firewall TCP/22 từ IAP không match, VM/SSH server lỗi | Xem tags, rules, trạng thái VM và OS log |
| `javac: command not found` | Chỉ cài runtime hoặc chưa cài JDK | Kiểm tra `java -version` và `javac -version` |
| `Module jdk.httpserver not found` | JRE/JDK image không chứa module | Cài JDK chuẩn tương thích rồi biên dịch lại |
| `Address already in use` | Đang chạy Java thủ công hoặc process khác chiếm 8080 | `ss -lntp`, dừng process thử trước systemd |
| `systemctl status` cho `failed` | Sai ExecStart, quyền JAR, JVM crash, unit syntax | `journalctl -u orders-api`, `systemd-analyze verify` |
| `curl localhost:8080` trên VM OK nhưng Cloud Shell tunnel lỗi | SSH -L chưa chạy, local port conflict hoặc sai project/zone | Kiểm tra port 18080 ở Cloud Shell, IAP tunnel |
| Cloud Shell tunnel OK nhưng Internet không truy cập được | Bài lab **không mở HTTP ingress**, app bind loopback | Đây là hành vi bảo mật đúng, không phải lỗi |
| Service chạy nhưng không có log trong Cloud Logging | Chưa cài/cấu hình Ops Agent hoặc thiếu IAM cho agent | Kiểm tra journal và pipeline log |
| API trả 500 với Cloud SQL production | Database auth, network, connection pool, app lỗi | Kiểm tra log, Cloud SQL private IP và secrets |
| VM dừng nhưng vẫn phát sinh phí | Disk, external IP/reservation, snapshot còn tồn tại | Billing report theo SKU |
| VM đơn lẻ mất kết nối khi reboot | Không có bản sao/HA | Thiết kế MIG nhiều zone và load balancer |

### 14.1. Luồng chẩn đoán theo lớp

~~~mermaid
flowchart TD
    A["Client không nhận được HTTP response"] --> B{"Đang thử qua IAP SSH -L?"}
    B -->|Không| C["Lab không expose HTTP công khai<br/>Dùng IAP tunnel hoặc thiết kế LB"]
    B -->|Có| D{"IAP/SSH kết nối được?"}
    D -->|Không| E["Kiểm tra IAM, IAP, OS Login, VM, firewall 22"]
    D -->|Có| F{"curl 127.0.0.1:8080 trên VM được?"}
    F -->|Không| G["systemctl, journalctl, ss, Java/JAR/port"]
    F -->|Có| H{"curl 127.0.0.1:18080 từ Cloud Shell được?"}
    H -->|Không| I["Kiểm tra local forwarding, cổng 18080, terminal"]
    H -->|Có| J["Lab OK; xác minh JSON, logs, reboot và cleanup"]
~~~

## 15. Dọn dẹp tài nguyên sau lab

**Bước dọn dẹp là bắt buộc** để hạn chế phát sinh chi phí không mong muốn. Đầu tiên kiểm tra rằng các tài nguyên trong `PROJECT_ID` đúng là của bài thực hành, không được chia sẻ cho workload khác. Đặt danh sách owner trước khi xóa.

Trong Cloud Shell (không phải terminal SSH trên VM):

~~~bash
# Xác minh định danh tài nguyên trước khi xóa.
gcloud compute instances describe java-orders-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a

# Xóa VM lab. Kiểm tra boot disk có bị xóa theo policy không.
gcloud compute instances delete java-orders-lab \
  --project=PROJECT_ID \
  --zone=asia-southeast1-a

# Xóa firewall của lab.
gcloud compute firewall-rules delete java-lab-allow-iap-ssh \
  --project=PROJECT_ID

# Xóa subnet trước rồi mới xóa VPC.
gcloud compute networks subnets delete java-lab-subnet \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud compute networks delete java-lab-vpc \
  --project=PROJECT_ID
~~~

Sau khi xác nhận service account không dùng cho ứng dụng khác, có thể xóa:

~~~bash
gcloud iam service-accounts delete \
  java-lab-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --project=PROJECT_ID
~~~

**Không xóa service account chỉ vì cùng tên** nếu nó được chia sẻ ngoài lab hoặc có owner khác. Sau cleanup, kiểm tra:

- **Compute Engine → VM instances, Disks, Snapshots** có tài nguyên còn sót không?
- **VPC network → IP addresses** có static external IP được reserve không?
- Có **Cloud NAT, Router, load balancer, Artifact Registry** nào tạo thêm trong biến thể lab không?
- Billing report có chi phí phát sinh do VM chạy trong thời gian thử; lưu ý báo cáo có độ trễ.

Các lệnh `delete` có thể yêu cầu xác nhận và thất bại nếu resource vẫn có dependency. **Không dùng cờ ép xóa** chỉ để vượt qua lỗi dependency mà chưa hiểu cái gì đang sử dụng tài nguyên.

## 16. Bài tập thực hành và câu hỏi tự đánh giá

### 16.1. Bài A — Vẽ lại luồng request

Dựa vào kiến trúc bài này, vẽ đường từ **Cloud Shell** tới `GET /api/orders` trên VM. Giải thích:

1. Vì sao cần IAP TCP forwarding khi dùng `--tunnel-through-iap`?
2. Vì sao VPC chỉ mở TCP/22 từ `35.235.240.0/20` mà API vẫn trả HTTP?
3. VM có external IPv4 có đồng nghĩa port 8080 public hay không?
4. Nếu không dùng external IPv4, cần chuẩn bị gì để `apt-get` tải gói từ Internet?

**Gợi ý:** HTTP chạy qua SSH port forwarding và dùng loopback VM; TCP/8080 không trực tiếp đi qua VPC ingress. VM private cần outbound phù hợp như Public NAT cho Internet IPv4.

### 16.2. Bài B — Đánh giá kết quả systemd

Giả sử lệnh:

~~~bash
sudo systemctl status orders-api --no-pager
~~~

trả:

~~~text
Active: failed (Result: exit-code)
...
java.net.BindException: Address already in use
~~~

Hãy nêu ít nhất ba bước chẩn đoán, bao gồm kiểm tra process đang dùng port, kiểm tra lần chạy thử Java và kiểm tra unit file. Có nên đổi `User=javaorders` thành `root` để sửa nhanh không? Vì sao?

**Gợi ý:** dùng `ss -lntp`, dừng Java thử và kiểm tra unit; đổi sang root không giải quyết port conflict và làm tăng rủi ro.

### 16.3. Bài C — Bảo mật service account

Nhóm phát triển muốn ứng dụng tải file từ Cloud Storage. Một thành viên đề xuất gán `roles/editor` cho runtime service account để “khỏi gặp lỗi”.

Hãy đề xuất:

- Quyền nào cần xem xét nếu ứng dụng chỉ đọc object từ bucket cụ thể?
- IAM binding nên cấp ở project hay bucket?
- Ứng dụng lấy thông tin xác thực ở VM thế nào nếu không lưu service account key JSON?
- Làm sao phân biệt `PERMISSION_DENIED` do IAM và lỗi do VPC/firewall?

**Gợi ý:** cân nhắc `roles/storage.objectViewer` ở đúng bucket theo cấu trúc quyền và operation cần thiết; dùng identity gắn VM/Application Default Credentials; kiểm tra error/permission cụ thể.

### 16.4. Bài D — Nâng cấp service không downtime

Sau khi triển khai demo một VM, khách hàng yêu cầu:

- Đáp ứng một zone gặp sự cố.
- Triển khai Java phiên bản mới mà không ngắt toàn bộ request.
- HTTPS và tên miền ổn định.
- Scale theo tải và theo dõi độ trễ p95.

Hãy mô tả kiến trúc tối thiểu gồm **regional MIG, instance templates, HTTPS load balancer, health checks, Cloud DNS và Monitoring**. Làm rõ cần thay đổi `BIND_HOST`, firewall backend, readiness, shutdown và artifact pipeline ra sao. So sánh với cách triển khai trên **Cloud Run**.

### 16.5. Bài E — Chi phí và cleanup

Một người làm lab tắt VM nhưng quên kiểm tra disk và external IP. Họ đã tạo snapshot và một static external IP không gắn VM.

1. Tắt VM có chắc đưa chi phí về 0 không?
2. Những mục nào phải kiểm tra trong Billing report?
3. Vì sao `gcloud compute instances delete` chưa đủ bảo đảm mọi tài nguyên lab đã được xóa?
4. Nêu một phương án tự động nhắc dọn dẹp và quản lý TTL sandbox theo chính sách tổ chức.

## 17. Checklist hoàn thành

- [ ] Đã chọn đúng project sandbox, region, zone và có budget/cảnh báo phù hợp.
- [ ] Đã tạo VPC custom và subnet không chồng lấn theo yêu cầu.
- [ ] Đã mở **chỉ SSH từ IAP** tới VM mục tiêu; không mở HTTP demo ra Internet.
- [ ] Đã tạo runtime service account riêng, không gán role quản trị rộng.
- [ ] Đã tạo VM Debian với machine type/boot disk/network được hiểu rõ.
- [ ] Đã đăng nhập qua IAP và kiểm tra OS Login/IAM.
- [ ] Đã cài JDK, biên dịch `OrdersApi.java` và đóng gói JAR.
- [ ] Đã thử `/healthz` và `/api/orders` ngay trong VM.
- [ ] Đã cấu hình Linux user không đặc quyền và unit `orders-api.service`.
- [ ] Đã xác minh systemd tự chạy, nhật ký qua `journalctl` và port đang bind loopback.
- [ ] Đã kiểm tra API từ Cloud Shell qua SSH `-L` và IAP.
- [ ] Đã phân biệt logging của systemd với Cloud Logging và metric OS/JVM.
- [ ] Đã mô tả được bản phát hành/rollback và cách chuyển sang MIG/load balancer.
- [ ] Đã phân biệt bảo mật Compute Engine VM, Cloud Run và database.
- [ ] Đã xóa tài nguyên lab sau kiểm tra owner và xác minh không còn chi phí không mong muốn.

## 18. Tài liệu chính thức

Trước khi chạy các lệnh trong Google Cloud thật, hãy đối chiếu cú pháp và trạng thái hỗ trợ của project/region/OS tại thời điểm triển khai:

- [Compute Engine: Create and start a VM instance](https://cloud.google.com/compute/docs/instances/create-start-instance)
- [Compute Engine: VM instance overview](https://cloud.google.com/compute/docs/instances)
- [Connect to Linux VMs using IAP TCP forwarding](https://cloud.google.com/iap/docs/using-tcp-forwarding)
- [OS Login overview](https://cloud.google.com/compute/docs/oslogin)
- [VPC firewall rules overview](https://cloud.google.com/firewall/docs/firewalls)
- [VPC networks and subnets](https://cloud.google.com/vpc/docs/vpc)
- [Cloud NAT overview](https://cloud.google.com/nat/docs/overview)
- [Service accounts attached to VMs](https://cloud.google.com/compute/docs/access/service-accounts)
- [Install and manage Ops Agent](https://cloud.google.com/stackdriver/docs/solutions/agents/ops-agent/installation)
- [Managed instance groups](https://cloud.google.com/compute/docs/instance-groups)
- [External Application Load Balancer overview](https://cloud.google.com/load-balancing/docs/https)
- [Compute Engine pricing](https://cloud.google.com/compute/vm-instance-pricing)
- [Cloud Billing budgets](https://cloud.google.com/billing/docs/how-to/budgets)
- [Java HttpServer module (JDK)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)

**Điểm cần nhớ:** triển khai Java trên Compute Engine không chỉ là chạy lệnh `java -jar`. Một triển khai có thể vận hành phải có **danh tính đúng, mạng được giới hạn, hệ điều hành và JVM được quản lý, tiến trình tự phục hồi, health check, logging, quy trình phát hành/rollback và khả năng kiểm soát chi phí**. Lab một VM giúp hiểu từng mắt xích; production cần thêm **HTTPS, xác thực, nhiều instance, load balancing, patching và monitoring** hoặc cân nhắc dịch vụ quản lý như Cloud Run nếu phù hợp.
