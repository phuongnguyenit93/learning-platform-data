# User data, startup script và cloud-init trong lần khởi động đầu

Khi tạo máy ảo, đội vận hành thường cần cài package, tạo tài khoản dịch vụ, ghi cấu hình, đăng ký agent giám sát và khởi động ứng dụng. Nếu thực hiện thủ công sau mỗi lần tạo máy, quy trình dễ sai khác giữa các instance và mất nhiều thời gian. Các nền tảng đám mây cung cấp cơ chế truyền dữ liệu khởi tạo vào máy ảo, thường được gọi là **user data**, **startup script** hoặc **custom data**. Trên Linux, **cloud-init** là công cụ phổ biến để đọc metadata và tự động thực hiện các bước khởi tạo đó.

Bài học này giải thích cách các cơ chế bootstrap hoạt động trong lần boot đầu, cách tổ chức script có thể chạy lặp an toàn, cách bảo vệ thông tin nhạy cảm và cách kiểm tra khi máy không hoàn tất khởi tạo. Mục tiêu là tạo được quy trình khởi động nhất quán, có thể kiểm thử và quan sát được trong môi trường VM.

## 1. Bootstrap là gì?

Bootstrap là quá trình chuẩn bị máy ảo để sẵn sàng chạy workload sau khi nền tảng cấp phát máy. Các bước thường gồm:

- Nhận diện môi trường và đọc metadata của instance.
- Cấu hình hostname, network hoặc thông tin môi trường.
- Tạo user và cấu hình quyền truy cập.
- Cài đặt package, runtime và agent cần thiết.
- Ghi file cấu hình cho ứng dụng.
- Lấy cấu hình hoặc secret từ dịch vụ quản lý phù hợp.
- Đăng ký máy với hệ thống giám sát, quản lý cấu hình hoặc service discovery.
- Khởi động dịch vụ và xác minh health check.

Bootstrap diễn ra sau khi VM được tạo và bắt đầu boot. Nó có thể chạy trong quá trình hệ điều hành khởi động hoặc thông qua agent/extension sau khi hệ điều hành đã hoạt động. Vì vậy, **VM ở trạng thái running chưa có nghĩa ứng dụng đã sẵn sàng**.

### Phân biệt image, user data và startup script

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Machine image | Cung cấp hệ điều hành và phần mềm nền đã chuẩn bị | Linux image có runtime, agent giám sát |
| User data / custom data | Dữ liệu hoặc chỉ thị được truyền vào khi tạo VM | Cloud-config, shell script, PowerShell |
| Startup script | Chương trình được thực thi trong giai đoạn khởi tạo hoặc lúc boot | Cài package, tạo cấu hình, khởi động dịch vụ |
| Cloud-init | Công cụ đọc datasource/metadata và điều phối các module khởi tạo trên Linux | Tạo user, ghi file, cài package, chạy lệnh |
| Configuration management | Quản lý cấu hình lâu dài sau bootstrap | Ansible, Puppet, Chef hoặc agent nội bộ |

Image nên chứa những thành phần nền ổn định và đã kiểm thử. User data thường cung cấp cấu hình riêng cho môi trường hoặc instance. Script khởi động thực hiện các thao tác cần thiết để kết nối hai phần đó.

Không nên đưa toàn bộ dữ liệu ứng dụng hoặc bí mật vào image hay user data. Những giá trị thay đổi theo môi trường nên được cấp qua metadata không nhạy cảm, hệ thống cấu hình hoặc secret manager với quyền truy cập giới hạn.

## 2. Luồng khởi động và vị trí của cloud-init

Một luồng boot Linux trên VM có thể khái quát như sau:

~~~mermaid
flowchart TD
    A["Cloud cấp phát VM từ image"] --> B["Firmware và bootloader"]
    B --> C["Kernel và init system"]
    C --> D["Network và dịch vụ nền"]
    D --> E["cloud-init phát hiện datasource"]
    E --> F["Đọc metadata và user data"]
    F --> G["Chạy các module bootstrap"]
    G --> H["Cài package, ghi cấu hình, tạo user"]
    H --> I["Khởi động ứng dụng và agent"]
    I --> J["Health check và readiness"]
    J --> K["VM được đưa vào phục vụ traffic"]
~~~

Chi tiết thực tế phụ thuộc image, hệ điều hành, agent của nhà cung cấp và cấu hình mạng. Trên nhiều image Linux cloud, cloud-init được tích hợp sẵn và chạy qua các service của systemd.

### Datasource và metadata

Cloud-init cần biết nó đang chạy trên môi trường nào và lấy dữ liệu khởi tạo từ đâu. Nguồn này được gọi là datasource. Trên cloud, datasource thường truy cập metadata service hoặc thông tin được nền tảng cung cấp cho instance.

Metadata có thể chứa:

- Instance ID và thông tin nhận diện máy.
- Region, zone hoặc project/account.
- Network interface và địa chỉ IP.
- Thông tin role hoặc identity được gán cho máy.
- User data hoặc custom data.
- Các thuộc tính phục vụ cấu hình môi trường.

Không phải datasource nào cũng cung cấp cùng trường dữ liệu. Script cần kiểm tra giá trị có tồn tại và xử lý trường hợp thiếu metadata.

### Metadata service là một ranh giới bảo mật

Metadata service thường chỉ nên được truy cập từ bên trong VM. Nếu ứng dụng có lỗ hổng SSRF (Server-Side Request Forgery), kẻ tấn công có thể cố truy cập metadata để lấy thông tin nhận diện hoặc credential tạm thời.

Các biện pháp giảm rủi ro:

- Dùng cơ chế bảo vệ metadata do nền tảng cung cấp, chẳng hạn token bắt buộc hoặc phiên bản metadata được bảo vệ.
- Không cho ứng dụng nhận URL tùy ý rồi gửi request từ máy chủ.
- Giới hạn quyền truy cập metadata trong ứng dụng và network namespace nếu nền tảng hỗ trợ.
- Gán instance role/service identity với quyền tối thiểu.
- Không lưu credential dài hạn trong file cấu hình.
- Theo dõi các lần truy cập metadata bất thường.

Trên AWS EC2, IMDSv2 dùng token cho request metadata và có thể được cấu hình bắt buộc. Đây là ví dụ cụ thể của cơ chế bảo vệ metadata; nền tảng khác có mô hình và tùy chọn riêng.

## 3. User data, custom data và startup script

Tên gọi thay đổi theo nhà cung cấp, nhưng ý tưởng chung là truyền dữ liệu hoặc chỉ thị vào VM khi tạo hoặc cấu hình máy.

### User data

User data thường được gắn với instance hoặc cấu hình launch. Nội dung có thể là:

- Shell script trên Linux.
- Cloud-config dành cho cloud-init.
- MIME multipart gồm nhiều loại nội dung.
- Dữ liệu văn bản hoặc cấu hình được agent nền tảng xử lý.

User data có thể được lưu trong metadata hoặc một cơ chế tương đương. Quyền đọc user data cần được kiểm soát vì nội dung có thể chứa thông tin cấu hình nội bộ.

### Startup script

Startup script là chương trình chạy khi máy khởi động hoặc trong một giai đoạn nhất định. Tùy nền tảng, script có thể được cung cấp qua metadata, extension, guest agent hoặc cấu hình của VM.

Cần phân biệt:

- Script chỉ chạy trong lần khởi tạo đầu.
- Script chạy mỗi lần máy boot.
- Script chạy theo sự kiện hoặc extension do người vận hành kích hoạt.
- Script được quản lý như service lâu dài của hệ điều hành.

Một script chạy mỗi boot phải an toàn khi thực thi nhiều lần. Nếu mỗi lần boot lại tạo user trùng, cài package không kiểm soát hoặc ghi đè dữ liệu runtime, máy có thể rơi vào trạng thái sai.

### Cloud-init

Cloud-init là công cụ khởi tạo phổ biến trên Linux cloud image. Nó đọc user data và datasource, sau đó chạy các module theo stage. Cloud-init hỗ trợ nhiều dạng đầu vào như cloud-config, shell script và MIME multipart.

Cloud-init có thể:

- Thiết lập hostname và user.
- Quản lý SSH authorized keys.
- Cài package.
- Ghi file.
- Chạy lệnh.
- Cấu hình một số thành phần hệ thống.
- Phát tín hiệu hoàn tất khởi tạo.

Cloud-init không phải công cụ quản lý mọi thay đổi cấu hình lâu dài. Nó phù hợp với khởi tạo ban đầu và một số tác vụ boot; các cấu hình cần liên tục hội tụ về trạng thái mong muốn nên được quản lý bằng configuration management hoặc hệ thống triển khai phù hợp.

## 4. Các stage chính của cloud-init

Cloud-init chia quá trình khởi tạo thành các stage để xử lý dữ liệu đúng thời điểm. Tên module và hành vi chi tiết có thể thay đổi theo phiên bản.

| Stage | Thời điểm khái quát | Công việc điển hình |
|---|---|---|
| Generator / Detect | Khi hệ thống chuẩn bị khởi động service cloud-init | Xác định service cần chạy và datasource |
| Local | Giai đoạn đầu, trước khi network hoàn chỉnh | Phát hiện datasource cục bộ, cấu hình một số thành phần nền |
| Network | Sau khi network sẵn sàng | Lấy metadata và user data, cấu hình network/user liên quan |
| Config | Giai đoạn cấu hình | Chạy module như ghi file và một số thiết lập hệ thống |
| Final | Giai đoạn cuối của boot | Cài package, chạy lệnh cuối, hoàn tất bootstrap |

### Local stage

Ở stage này, cloud-init phát hiện datasource và thực hiện một số công việc không cần network đầy đủ. Tác vụ phụ thuộc endpoint bên ngoài chưa nên được giả định là có thể chạy tại đây.

### Network stage

Khi network đã sẵn sàng, cloud-init có thể truy vấn metadata service, lấy user data và xử lý cấu hình cần thông tin từ nền tảng. Nếu network chưa hoạt động hoặc metadata endpoint không truy cập được, quá trình có thể bị chậm hoặc thất bại.

### Config stage

Các module cấu hình như **write_files** có thể ghi file vào hệ thống. Thứ tự giữa các module quan trọng: file cấu hình cần tồn tại trước khi service được khởi động.

### Final stage

Các tác vụ cài package và chạy lệnh cuối thường được thực hiện ở stage này. Tác vụ tải dữ liệu lớn hoặc cài nhiều package có thể kéo dài thời gian boot.

**runcmd** trong cloud-config được ghi nhận ở giai đoạn cấu hình và thực thi ở final stage thông qua cơ chế script của cloud-init. Vì vậy, không nên dùng nó để giả định một lệnh đã hoàn tất ngay sau khi file user data được đọc.

### First boot và các lần boot tiếp theo

Cloud-init lưu trạng thái để xác định module nào đã chạy và tần suất thực thi. Một số module chạy một lần cho mỗi instance; một số module chạy mỗi boot hoặc mỗi lần cấu hình. User-data script thông thường được xử lý theo chính sách tần suất của cloud-init, thường là một lần cho mỗi instance.

Các chỉ thị như **bootcmd** có thể chạy ở mỗi lần boot, còn **runcmd** thường chạy một lần cho mỗi instance. Có thể dùng các thư mục script theo tần suất hoặc module tương ứng, nhưng cần kiểm tra phiên bản cloud-init và cấu hình image.

Không dùng **cloud-init clean** như cách sửa lỗi thường xuyên trên máy production. Lệnh này xóa trạng thái cloud-init và có thể khiến các bước khởi tạo chạy lại ở lần boot sau. Nó thường được dùng có chủ đích khi chuẩn bị image mẫu hoặc tái tạo trạng thái first boot.

## 5. Viết cloud-config với YAML

Cloud-config là định dạng user data có header **#cloud-config**. Nội dung YAML mô tả trạng thái hoặc các thao tác cần thực hiện.

Ví dụ sau minh họa tạo user, cài package, ghi file cấu hình và chạy một lệnh khởi tạo:

~~~yaml
#cloud-config

package_update: true

packages:
  - nginx
  - curl

users:
  - default
  - name: appops
    shell: /bin/bash
    lock_passwd: true
    ssh_authorized_keys:
      - ssh-ed25519 AAAA...replace-with-approved-public-key

write_files:
  - path: /etc/example-app/bootstrap.conf
    owner: root:root
    permissions: "0640"
    content: |
      APP_ENV=staging
      LOG_LEVEL=info

runcmd:
  - [systemctl, enable, nginx]
  - [systemctl, start, nginx]
~~~

Đây là ví dụ minh họa. Cần xác minh package, user mặc định, shell, nhóm quyền và module cloud-init của image thực tế. Không dùng public key giả trong production; thay bằng khóa công khai được tổ chức phê duyệt.
Tài khoản ứng dụng trong ví dụ không được cấp quyền quản trị. Nếu cần tài khoản vận hành có quyền nâng cao, hãy cấp qua nhóm và policy được phê duyệt, giới hạn phạm vi lệnh và ghi audit.

### Lưu ý với YAML

- Thụt lề bằng khoảng trắng và giữ cấu trúc nhất quán.
- Chuỗi có ký tự đặc biệt nên được đặt trong dấu nháy phù hợp.
- Quyền file nên ghi dưới dạng chuỗi, ví dụ **0640**, để tránh YAML diễn giải thành số.
- Nội dung nhiều dòng dùng block scalar dạng pipe hoặc greater-than.
- Không đặt private key, password hoặc token trong ví dụ hay user data.
- Kiểm tra cú pháp bằng công cụ cloud-init trước khi tạo nhiều máy.

Có thể kiểm tra cấu hình trên Linux bằng:

~~~sh
cloud-init schema --config-file user-data.yaml
~~~

Khả năng của lệnh kiểm tra phụ thuộc phiên bản cloud-init. Nên kiểm tra schema trong image hoặc môi trường gần giống production.

## 6. Viết shell startup script an toàn

Một số nền tảng chấp nhận shell script bắt đầu bằng shebang. Script cần khai báo shell rõ ràng và xử lý lỗi có chủ đích.

Ví dụ đơn giản:

~~~bash
#!/usr/bin/env bash
set -Eeuo pipefail

LOG_FILE=/var/log/app-bootstrap.log
exec > >(tee -a "$LOG_FILE") 2>&1

if ! command -v nginx >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y nginx
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y nginx
  else
    echo "Unsupported package manager" >&2
    exit 1
  fi
fi

install -d -o root -g root -m 0755 /opt/example-app

systemctl enable nginx
systemctl start nginx

systemctl is-active --quiet nginx
~~~

Script này minh họa các nguyên tắc:

- Dùng shebang để xác định interpreter.
- Dừng khi có lỗi ngoài dự kiến.
- Ghi log để hỗ trợ điều tra.
- Kiểm tra package trước khi cài.
- Tạo thư mục và file theo trạng thái mong muốn.
- Enable và start service theo cách có thể chạy lại.
- Kiểm tra trạng thái dịch vụ ở cuối.

Trong production, cần bổ sung timeout, retry có giới hạn cho các phụ thuộc mạng, xác minh chữ ký hoặc checksum của artifact và xử lý lỗi theo từng bước. Không dùng lệnh tải rồi thực thi script trực tiếp từ nguồn không được xác minh.

### Idempotency là yêu cầu quan trọng

Idempotent nghĩa là chạy cùng một thao tác nhiều lần vẫn đưa hệ thống về cùng trạng thái mong muốn, không tạo thêm tác dụng phụ ngoài ý muốn.

Ví dụ:

- Tạo thư mục bằng **install -d** hoặc **mkdir -p**.
- Kiểm tra package đã cài trước khi cài.
- Ghi file theo nội dung xác định thay vì nối thêm mỗi lần.
- Dùng **systemctl enable** và kiểm tra service.
- Tạo user theo cơ chế kiểm tra tồn tại.
- Dùng marker hoặc state có phiên bản khi cần kiểm soát tác vụ đã hoàn tất.

Marker file đơn giản không đủ để chứng minh toàn bộ bootstrap thành công. Nếu script dừng giữa chừng sau khi tạo marker, lần chạy sau có thể bỏ qua các bước chưa hoàn tất. Chỉ ghi marker sau khi tất cả kiểm tra cần thiết đạt, hoặc quản lý trạng thái riêng cho từng bước.

### Không dùng startup script làm hệ thống triển khai ứng dụng lâu dài

Startup script có thể tải và khởi chạy phiên bản ứng dụng ban đầu, nhưng mỗi lần phát hành mới không nên phụ thuộc vào việc sửa user data thủ công. Dùng CI/CD, configuration management hoặc deployment agent để quản lý release và rollback.

## 7. Thứ tự và phụ thuộc giữa các bước bootstrap

Một số bước phải hoàn tất trước bước khác. Ví dụ:

1. Network hoạt động.
2. Metadata và identity được đọc.
3. Quyền truy cập secret/artifact được xác định.
4. Package và runtime được cài.
5. File cấu hình được ghi.
6. Ứng dụng được cài hoặc tải về.
7. Service được enable/start.
8. Health check đạt.
9. Load balancer đưa máy vào phục vụ.

Nếu ứng dụng khởi động trước khi file cấu hình được ghi, service có thể crash. Nếu script tải artifact trước khi DNS hoặc route sẵn sàng, lệnh tải sẽ thất bại.

### Kiểm soát phụ thuộc mạng

Bootstrap thường cần truy cập package repository, artifact registry, secret manager hoặc hệ thống quản trị. Cần bảo đảm:

- DNS hoạt động.
- Route và firewall cho phép kết nối cần thiết.
- Proxy hoặc private endpoint được cấu hình nếu dùng.
- Chứng thư CA cần thiết đã có.
- Endpoint dịch vụ có thể truy cập từ subnet của VM.
- Có retry/backoff cho lỗi tạm thời và timeout tổng thể.

Không retry vô hạn. Một endpoint sai hoặc policy chặn sẽ khiến VM treo ở trạng thái khởi tạo quá lâu. Hãy giới hạn thời gian, ghi log và phát tín hiệu thất bại để hệ thống điều phối xử lý.

### Không dựa vào thứ tự ngẫu nhiên

Nếu nhiều script hoặc module cùng sửa một file, cài cùng package hoặc khởi động cùng service, kết quả có thể phụ thuộc thứ tự chạy. Tổ chức bootstrap thành các bước rõ ràng, có đầu vào/đầu ra và kiểm tra sau mỗi giai đoạn.

## 8. Quản lý secret và danh tính máy

User data có thể được lưu trong metadata, cấu hình instance, API hoặc log của nền tảng. Vì vậy, nội dung này có thể được đọc bởi người có quyền quản lý VM hoặc quyền metadata tương ứng.

Không đưa trực tiếp vào user data:

- Password database.
- Private key.
- Access key dài hạn.
- Token của hệ thống CI/CD.
- Chứng thư riêng.
- Bí mật mã hóa hoặc chuỗi kết nối có credential.

### Lấy secret khi runtime

Một mô hình an toàn hơn:

1. Gán instance role, managed identity hoặc service account cho VM.
2. Cấp quyền tối thiểu để đọc đúng secret cần thiết.
3. Khi bootstrap, lấy credential tạm thời hoặc secret từ secret manager.
4. Ghi secret vào vị trí cần thiết với owner và permission chặt chẽ, hoặc chuyển trực tiếp qua cơ chế an toàn.
5. Tránh ghi giá trị secret ra log, command line hoặc file world-readable.
6. Xoay vòng secret theo chính sách.

Không dùng credential của người vận hành được nhúng trong script để gọi cloud API. Hãy dùng danh tính workload do nền tảng cấp.

### Tách cấu hình khỏi bí mật

Cấu hình thông thường như tên môi trường, port, feature flag hoặc endpoint không nhạy cảm có thể được truyền qua user data hoặc configuration service. Bí mật cần đi qua secret manager với quyền và audit riêng.

Khi log bootstrap, chỉ ghi trạng thái như “đã lấy cấu hình” hoặc định danh secret, không in giá trị secret.

## 9. Bootstrap trên AWS, Azure và Google Cloud

Các nền tảng có cơ chế riêng. Không nên giả định user data có cùng giới hạn kích thước, thời điểm thực thi hoặc tần suất chạy.

| Nền tảng | Cơ chế phổ biến | Điểm cần xác minh |
|---|---|---|
| AWS EC2 | User data; cloud-init trên nhiều Linux AMI; EC2Launch trên Windows | User data script thường chạy ở lần launch đầu theo cấu hình mặc định; giới hạn kích thước, IMDSv2, log và agent |
| Microsoft Azure | Custom data, cloud-init trên Linux image hỗ trợ, VM Agent và Custom Script Extension | Phân biệt custom data với extension; trạng thái provisioning; khả năng chạy lại và giới hạn dữ liệu |
| Google Cloud | Startup scripts qua metadata, guest environment/agent; cloud-init trên image hỗ trợ | Script chạy lúc boot theo loại khóa metadata; quyền service account, log và guest agent |

### AWS EC2

Trên nhiều Linux AMI, EC2 user data được cloud-init xử lý. Có thể truyền shell script hoặc cloud-config khi tạo instance. User data script thường chỉ chạy trong lần khởi tạo đầu theo mặc định của image/cấu hình; muốn chạy mỗi boot cần dùng cơ chế phù hợp và hiểu tác động của nó.

Trên Windows, EC2Launch hoặc công cụ khởi tạo tương ứng xử lý user data. Hành vi phụ thuộc phiên bản agent và cấu hình. Không áp dụng giả định của cloud-init Linux cho Windows.

Kiểm tra log cloud-init trên Linux thường gồm:

~~~sh
cloud-init status --long
sudo less /var/log/cloud-init.log
sudo less /var/log/cloud-init-output.log
~~~

### Microsoft Azure

Azure Linux VM có thể dùng cloud-init khi image hỗ trợ và custom data được truyền lúc provision. VM Agent và Custom Script Extension là cơ chế khác, thường được dùng để chạy script hoặc triển khai cấu hình sau khi máy đã được tạo.

Custom data và extension không có cùng vòng đời. Nếu cần chạy lại một tác vụ sau khi VM đã provision, extension hoặc công cụ quản lý cấu hình thường phù hợp hơn việc kỳ vọng custom data tự chạy lại.

Trên Windows, có thể dùng VM Agent và extension như Custom Script Extension để chạy PowerShell. Cần kiểm tra trạng thái extension trong Azure Portal/CLI và log của VM Agent.

### Google Cloud

Compute Engine hỗ trợ startup scripts qua metadata keys ở cấp project hoặc instance. Guest environment/agent trên VM đọc metadata và thực thi script theo quy tắc của nền tảng. Linux image có thể dùng cloud-init nếu datasource và image được cấu hình tương thích.

Một số startup script được thực thi mỗi lần VM boot, do đó phải idempotent. Cần phân biệt các key startup script cho Linux và Windows, cũng như phạm vi metadata ở project so với instance.

### Lựa chọn cơ chế

- Dùng cloud-init khi cần khởi tạo Linux theo cấu trúc module và image hỗ trợ tốt.
- Dùng startup script khi thao tác đơn giản và nền tảng cung cấp cơ chế thực thi rõ ràng.
- Dùng extension hoặc configuration management khi cần chạy lại, theo dõi trạng thái và quản lý thay đổi sau lần boot đầu.
- Dùng image đã bake sẵn package nặng khi muốn giảm thời gian bootstrap và phụ thuộc repository lúc boot.

## 10. Bootstrap cho Windows

Windows VM thường dùng agent hoặc extension của nhà cung cấp để xử lý custom data và startup script. Script thường được viết bằng PowerShell và có thể chạy với quyền hệ thống tùy cơ chế.

Ví dụ PowerShell minh họa kiểm tra và tạo thư mục:

~~~powershell
$ErrorActionPreference = "Stop"

$LogPath = "C:\ProgramData\ExampleApp\bootstrap.log"
$Directory = "C:\ProgramData\ExampleApp"

New-Item -ItemType Directory -Path $Directory -Force | Out-Null

"Bootstrap started at $(Get-Date -Format o)" |
  Out-File -FilePath $LogPath -Append -Encoding utf8

if (-not (Test-Path "C:\Program Files\ExampleApp\app.exe")) {
    # Cài đặt artifact đã được xác minh bằng quy trình nội bộ.
    Write-Output "Application installation is required."
}

"Bootstrap checks completed at $(Get-Date -Format o)" |
  Out-File -FilePath $LogPath -Append -Encoding utf8
~~~

Trong production, nên dùng installer có chữ ký, xác minh checksum, timeout và exit code. Không tắt kiểm tra TLS hoặc thực thi script tải về không xác minh. Nếu script có thể chạy lại, mọi bước cần kiểm tra trạng thái trước khi thay đổi.

### Kiểm tra log và trạng thái Windows

Tùy agent và image, log có thể nằm trong thư mục ProgramData của nhà cung cấp hoặc được ghi vào Windows Event Log. Có thể kiểm tra:

- Trạng thái VM Agent và extension.
- Exit code của script.
- Event Viewer, đặc biệt các log liên quan đến provisioning và service.
- Trạng thái service ứng dụng.
- Các file log do bootstrap script tạo.

Đường dẫn cụ thể khác nhau theo phiên bản agent. Hãy dùng tài liệu của image và extension đang triển khai.

## 11. Bootstrap với systemd

Sau khi cài ứng dụng, nên quản lý tiến trình dài hạn bằng service manager của hệ điều hành. Trên Linux, systemd giúp khai báo thứ tự khởi động, user chạy service, restart policy và dependency.

Ví dụ unit file:

~~~ini
[Unit]
Description=Example application
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=appuser
Group=appuser
WorkingDirectory=/opt/example-app
ExecStart=/opt/example-app/bin/server
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
~~~

Sau khi ghi unit file, bootstrap có thể chạy:

~~~sh
systemctl daemon-reload
systemctl enable example-app.service
systemctl start example-app.service
systemctl status example-app.service --no-pager
~~~

**network-online.target** chỉ hữu ích khi hệ thống có dịch vụ wait-online phù hợp. Nó không bảo đảm mọi endpoint bên ngoài đã sẵn sàng. Ứng dụng vẫn cần retry kết nối dependency và có timeout.

### Readiness khác với process đang chạy

Một service có trạng thái active chưa chắc đã sẵn sàng nhận request. Readiness cần kiểm tra các điều kiện thực tế như:

- Ứng dụng đã nạp cấu hình.
- Kết nối database hoặc dependency cần thiết đã hoạt động.
- Cache hoặc dữ liệu bắt buộc đã warm-up.
- Port và endpoint health check phản hồi.
- Không còn bước migration hoặc initialization quan trọng đang chạy.

Load balancer nên chỉ gửi traffic khi readiness đạt. Nếu bootstrap thất bại, instance không nên được đưa vào pool chỉ vì VM đã chuyển sang trạng thái running.

## 12. Theo dõi trạng thái bootstrap

Bootstrap nên tạo ra trạng thái quan sát được. Một pipeline tạo VM cần phân biệt các mốc:

1. VM được cấp phát.
2. VM bắt đầu boot.
3. Network và metadata hoạt động.
4. Bootstrap bắt đầu.
5. Các bước cài đặt và cấu hình hoàn tất.
6. Ứng dụng khởi động.
7. Readiness đạt.
8. VM được phép nhận traffic.

Cloud provider có thể báo VM ở trạng thái running hoặc provisioning succeeded trước khi ứng dụng hoàn tất. Cần dùng tín hiệu riêng cho bootstrap và ứng dụng.

### Log cloud-init trên Linux

Các lệnh hữu ích:

~~~sh
cloud-init status --long
sudo journalctl -u cloud-init-local
sudo journalctl -u cloud-init
sudo journalctl -u cloud-config
sudo journalctl -u cloud-final
sudo tail -n 200 /var/log/cloud-init.log
sudo tail -n 200 /var/log/cloud-init-output.log
~~~

Tên unit có thể khác theo bản phân phối. Không phải image nào cũng có tất cả service hoặc giữ log theo cùng cách.

### Phân tích thời gian chạy

Cloud-init có thể cung cấp công cụ phân tích stage và module:

~~~sh
cloud-init analyze show
cloud-init analyze blame
~~~

Kết quả giúp xác định bước nào kéo dài thời gian boot. Nếu cài package mất nhiều phút, có thể cân nhắc bake package vào image, dùng repository nội bộ hoặc giảm số tác vụ đồng thời.

### Phát tín hiệu hoàn tất

Một số nền tảng hỗ trợ cơ chế signal hoặc trạng thái extension để báo bootstrap thành công/thất bại. Nếu tự xây dựng, có thể gửi metric/event tới hệ thống giám sát sau mỗi giai đoạn.

Tín hiệu cần chứa instance ID, image version, bootstrap version và trạng thái, nhưng không chứa secret. Dùng timeout tổng thể để hệ thống điều phối phát hiện máy bị treo ở bước khởi tạo.

## 13. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Script không chạy | User data sai định dạng, thiếu shebang, agent/cloud-init không hoạt động | Kiểm tra user data, service cloud-init hoặc VM agent và log |
| Không lấy được metadata | Network, route, firewall hoặc metadata policy | Kiểm tra datasource, endpoint metadata và cấu hình bảo vệ |
| Cài package thất bại | DNS, repository, proxy, TLS hoặc package lock | Kiểm tra log package manager, DNS, route và thời gian chờ |
| YAML cloud-config không được áp dụng | Sai indentation, key/module không hỗ trợ hoặc header sai | Kiểm tra schema, phiên bản cloud-init và log |
| Script chạy nhiều lần | Startup script được cấu hình chạy mỗi boot hoặc instance state bị reset | Xác định tần suất thực thi, thiết kế idempotent và marker đúng cách |
| VM running nhưng ứng dụng chưa sẵn sàng | Bootstrap vẫn chạy, service lỗi hoặc dependency chưa sẵn sàng | Kiểm tra readiness, systemd, log ứng dụng và dependency |
| Bootstrap treo lâu | Retry vô hạn, tải lớn hoặc endpoint không phản hồi | Đặt timeout, backoff, deadline và log từng bước |
| Secret không truy cập được | Role/identity hoặc policy thiếu quyền | Kiểm tra identity gắn với VM và audit log secret manager |
| Instance mới có hostname hoặc SSH host key trùng | Image chưa generalize hoặc trạng thái máy mẫu bị giữ lại | Rà soát quy trình image build và first-boot identity |
| Extension báo lỗi | VM agent cũ, handler không tương thích hoặc script exit code khác 0 | Kiểm tra agent, extension status, handler log và exit code |

### Quy trình điều tra theo thứ tự

1. Xác định VM đã boot đến hệ điều hành chưa.
2. Kiểm tra network và metadata service.
3. Xác minh user data đúng định dạng và có được agent nhận hay không.
4. Đọc log cloud-init/VM agent từ đầu đến cuối.
5. Xác định module hoặc lệnh đầu tiên thất bại.
6. Chạy lại riêng lệnh đó trong môi trường kiểm thử để tái hiện.
7. Kiểm tra quyền, package repository, DNS và dependency.
8. Sửa script theo hướng idempotent, có timeout và log.
9. Tạo instance thử mới để xác nhận first boot.
10. Chỉ phát hành image hoặc cấu hình sau khi smoke test đạt.

Không chỉnh trạng thái nội bộ cloud-init hoặc xóa file state tùy tiện trên production để ép script chạy lại. Cách đó có thể khiến module tạo user, SSH key hoặc cấu hình hệ thống chạy lại ngoài dự kiến.

## 14. Bảo mật và vận hành đáng tin cậy

Bootstrap thường chạy với quyền root hoặc SYSTEM. Một lỗi trong script có thể ảnh hưởng toàn bộ máy, vì vậy cần áp dụng nguyên tắc an toàn từ lúc thiết kế.

### Quyền tối thiểu

- Script chỉ có quyền cần thiết cho các bước được giao.
- Instance role chỉ được đọc đúng artifact, secret và cấu hình cần dùng.
- Không dùng chung credential quản trị giữa các môi trường.
- File cấu hình có owner và permission rõ ràng.
- Service ứng dụng chạy bằng user riêng, không chạy root nếu không cần.

### Kiểm soát nguồn script và artifact

- Lưu script trong repository có review và version control.
- Dùng artifact registry hoặc nguồn nội bộ đáng tin cậy.
- Xác minh checksum hoặc chữ ký trước khi cài.
- Ghim phiên bản package hoặc artifact khi cần tái tạo.
- Quét lỗ hổng và kiểm tra license.
- Ghi nhận image version và bootstrap version trong inventory.

### Hạn chế phụ thuộc lúc boot

Nếu mỗi VM phải tải hàng chục package từ Internet trước khi phục vụ traffic, thời gian khởi động sẽ khó dự đoán. Có thể:

- Bake runtime và package nền vào image.
- Dùng repository hoặc artifact mirror nội bộ.
- Tải song song các thành phần độc lập nhưng có giới hạn.
- Cache artifact ở region gần VM.
- Chỉ tải cấu hình nhỏ và secret cần thiết lúc boot.

Không bake dữ liệu bí mật hoặc credential vào image để giảm thời gian khởi động. Secret vẫn nên được lấy bằng workload identity khi runtime.

### Kiểm soát thay đổi user data

User data thường gắn với cấu hình tạo máy hoặc metadata. Sửa nội dung sau khi VM đã chạy không có nghĩa script tự chạy lại. Có nền tảng chỉ cho thay đổi dữ liệu nhưng không tự kích hoạt, có nền tảng yêu cầu reboot hoặc cơ chế riêng.

Với thay đổi bootstrap, nên tạo phiên bản mới, thử trên instance mới và triển khai qua launch template/scale set/instance group hoặc quy trình thay thế phù hợp. Ghi lại phiên bản script để có thể truy vết.

## 15. Ví dụ: bootstrap một dịch vụ web trên Linux

Một nhóm triển khai dịch vụ web trên nhiều VM. Image nền đã có cloud-init và agent bảo mật. User data chứa cấu hình môi trường không nhạy cảm, còn secret được lấy từ secret manager bằng instance identity.

Luồng triển khai:

1. Tạo VM từ image đã được kiểm thử.
2. cloud-init phát hiện datasource và đọc user data.
3. Cấu hình hostname và tạo user ứng dụng.
4. Cài package còn thiếu và ghi file cấu hình.
5. Lấy secret runtime bằng identity được cấp.
6. Tải artifact ứng dụng từ registry nội bộ và xác minh checksum.
7. Cài systemd unit và enable service.
8. Khởi động ứng dụng.
9. Kiểm tra health endpoint và gửi trạng thái bootstrap.
10. Load balancer đưa VM vào pool khi readiness đạt.

Một phần cloud-config có thể như sau:

~~~yaml
#cloud-config

package_update: true
packages:
  - curl
  - jq

users:
  - default
  - name: appuser
    system: true
    shell: /usr/sbin/nologin
    lock_passwd: true

write_files:
  - path: /etc/example-app/app.env
    owner: root:appuser
    permissions: "0640"
    content: |
      APP_ENV=production
      PORT=8080

runcmd:
  - [install, -d, -o, appuser, -g, appuser, /opt/example-app]
  - [systemctl, daemon-reload]
  - [systemctl, enable, example-app.service]
  - [systemctl, start, example-app.service]
~~~

Ví dụ giả định artifact và systemd unit đã được cung cấp qua image hoặc bước triển khai khác. Không đưa secret vào app.env trong user data; ứng dụng hoặc một bước runtime có quyền phù hợp cần lấy secret an toàn.

Nếu dịch vụ không đạt health check, VM cần được giữ ngoài load balancer. Pipeline có thể thu log, đánh dấu instance thất bại và tạo máy mới sau khi xử lý nguyên nhân.

## 16. Quy trình thiết kế và kiểm thử bootstrap

Một quy trình có thể áp dụng cho VM production:

1. **Xác định mục tiêu:** liệt kê package, user, cấu hình, secret và dịch vụ cần có trước khi nhận traffic.
2. **Chọn cơ chế:** cloud-init, user data script, startup script hay extension dựa trên hệ điều hành và nhà cung cấp.
3. **Chia giai đoạn:** phân tách việc không cần mạng, việc cần metadata, cài package, cấu hình và khởi động service.
4. **Thiết kế idempotent:** chạy lại không tạo user trùng, nối file lặp hoặc gây mất dữ liệu.
5. **Giới hạn quyền:** dùng instance identity, secret manager và permission tối thiểu.
6. **Thêm quan sát:** log theo bước, timeout, exit code, metric và tín hiệu hoàn tất.
7. **Kiểm thử image sạch:** tạo VM mới từ image thực tế và xác minh first boot.
8. **Kiểm thử lỗi:** mô phỏng DNS lỗi, repository không truy cập được, secret thiếu quyền và artifact không tồn tại.
9. **Đo thời gian:** xác định bước chậm và đặt ngưỡng bootstrap tối đa.
10. **Phát hành có kiểm soát:** triển khai canary, theo dõi readiness và giữ khả năng rollback.

### Tiêu chí hoàn tất bootstrap

Một VM chỉ nên được đánh dấu sẵn sàng khi:

- Hệ điều hành boot hoàn tất.
- Bootstrap kết thúc với exit status thành công.
- Runtime và cấu hình cần thiết đã có.
- Secret được lấy bằng danh tính hợp lệ.
- Ứng dụng khởi động và readiness check đạt.
- Agent giám sát và bảo mật hoạt động.
- VM được đăng ký với hệ thống điều phối.
- Không có lỗi nghiêm trọng trong log khởi tạo.

## 17. Checklist trước khi đưa user data vào production

- [ ] Đã chọn đúng cơ chế theo image, hệ điều hành và cloud provider.
- [ ] Đã phân biệt tác vụ first boot với tác vụ mỗi lần boot.
- [ ] Đã kiểm tra datasource và metadata service.
- [ ] Đã xác minh cấu trúc cloud-config hoặc shell/PowerShell syntax.
- [ ] Script có timeout, xử lý lỗi và log theo từng bước.
- [ ] Các bước có thể chạy lại an toàn hoặc có trạng thái kiểm soát rõ.
- [ ] Thứ tự phụ thuộc network, package, file và service được xác định.
- [ ] Không có password, private key, token hoặc secret trong user data.
- [ ] Instance identity chỉ có quyền tối thiểu.
- [ ] Artifact được lấy từ nguồn tin cậy và xác minh tính toàn vẹn.
- [ ] Service chạy bằng user phù hợp và có restart policy.
- [ ] Có readiness check riêng với trạng thái VM running.
- [ ] Có log, metric, exit code và timeout tổng thể.
- [ ] Đã thử trên instance mới từ image production.
- [ ] Đã thử các tình huống lỗi và cách khôi phục.
- [ ] Có version cho image, user data và bootstrap script.
- [ ] Có kế hoạch rollout, rollback và lưu trữ log.

## Kết luận

User data truyền cấu hình hoặc chỉ thị vào VM; startup script thực hiện các thao tác khởi tạo; cloud-init điều phối nhiều bước bootstrap trên Linux thông qua datasource và các stage. Để quá trình khởi động đáng tin cậy, cần xác định đúng thời điểm chạy, thứ tự phụ thuộc, tần suất thực thi và điều kiện hoàn tất. Script phải idempotent, có timeout và log, dùng danh tính máy để lấy secret, đồng thời kiểm tra readiness trước khi nhận traffic. Kết hợp image đã chuẩn hóa, bootstrap có version và kiểm thử trên instance mới giúp triển khai VM nhất quán, dễ điều tra và an toàn hơn.
