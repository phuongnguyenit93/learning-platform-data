# Export options và kiểm soát truy cập theo mạng

Trong chương **File Storage** của module Oracle Cloud Infrastructure (OCI), bài này giải quyết một yêu cầu triển khai cụ thể: nhiều máy Linux cần dùng chung filesystem, nhưng có máy được ghi, có máy chỉ được đọc và có máy không được truy cập. Đồng thời, tài khoản root trên một client không được tự có đầy đủ đặc quyền đối với dữ liệu dùng chung.

Ta sử dụng NFS export options cùng VCN security rules và quyền UNIX. Ví dụ thực hành dùng NFSv3 với `AUTH_SYS`, các địa chỉ IPv4 nội bộ và một filesystem lab. Đây là cấu hình để học cách kiểm soát truy cập; môi trường cần xác thực người dùng mạnh hoặc mã hóa đường truyền có thêm lựa chọn Kerberos/TLS phải được thiết kế tương ứng.

Sau bài học, người học có thể:

- Phân biệt quyền quản trị OCI với quyền kết nối NFS và quyền đọc/ghi file.
- Chọn Source CIDR, kiểu truy cập, source port và identity squash phù hợp.
- Giải thích thứ tự áp dụng entry khi CIDR chồng lấn.
- Cấu hình các lớp mạng và export riêng biệt, rồi kiểm tra cả truy cập được phép và bị từ chối.
- Cập nhật chính sách có kiểm soát, không bỏ sót export khác trỏ tới cùng filesystem.

## 1. Từ client đến dữ liệu: các lớp kiểm soát khác nhau

Một yêu cầu đọc file đi qua nhiều điều kiện:

```text
Client có đường đi tới mount target
  -> lưu lượng được các lớp mạng cho phép
  -> source của client khớp export option phù hợp
  -> kiểu xác thực và source port được chấp nhận
  -> UID/GID sau ánh xạ có quyền đối với file/thư mục
```

| Lớp | Kiểm soát điều gì? | Ví dụ |
|---|---|---|
| IAM OCI | Ai được tạo/sửa tài nguyên dịch vụ | Người vận hành được cập nhật export options |
| Routing và bảo vệ mạng | Client nào kết nối được tới mount target | Chỉ nhóm máy ứng dụng được tới các cổng NFS/RPC |
| Export options | Cách một source truy cập qua một export | Máy A đọc/ghi, máy B chỉ đọc |
| Danh tính NFS và quyền UNIX | Người dùng nào thực hiện được thao tác trên file | UID 2000 được ghi vào thư mục thuộc UID/GID tương ứng |

Các lớp này có vai trò riêng. IAM cho phép sửa filesystem trên Console không tự cấp quyền đọc nội dung file qua NFS; tài khoản root trong VM cũng không tự có quyền sửa export trên OCI. [Nguồn: các lớp bảo mật File Storage](https://docs.oracle.com/en-us/iaas/Content/File/Concepts/securitylayers.htm).

Ví dụ, một client có thể mount thành công nhưng không ghi được vì thư mục không cho UID đó ghi. Ngược lại, mode `0777` trên một thư mục không giúp client vượt qua một export chỉ cho đọc hoặc một đường mạng bị chặn.

Phải kiểm tra từng lớp bằng bằng chứng phù hợp. Chỉ thấy mount thành công chưa chứng minh yêu cầu phân quyền đã đúng.

## 2. File system, mount target, export và export path

Những đối tượng cần nhận diện:

- **File system** chứa cây thư mục và dữ liệu.
- **Mount target** là điểm kết nối NFS trên mạng.
- **Export set** gắn với mount target và chứa các export.
- **Export** liên kết filesystem với export path và chính sách client.
- **Export options** là danh sách entry quy định quyền cho các source.

Một filesystem có thể được đưa ra qua nhiều export/mount target. Chính sách gắn với export đang được sử dụng, nên khi kiểm tra truy cập cần ghi cả filesystem OCID, export OCID, mount target và đường dẫn đang mount. [Nguồn: OCI exports và export options](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/exportoptions.htm).

Ví dụ kết nối:

```text
10.40.20.10:/shared-lab  ->  /mnt/fss-lab trên client
```

Trong đó `10.40.20.10` là IP mount target, `/shared-lab` là export path và `/mnt/fss-lab` là mount point cục bộ. Ba giá trị có vai trò khác nhau; tên export path không tự tạo một thư mục cùng tên bên trong filesystem. [Nguồn: paths in file systems](https://docs.oracle.com/en-us/iaas/Content/File/Concepts/filesystempaths.htm).

Nếu ứng dụng đang mount một export khác cùng filesystem, sửa export mà người vận hành đang nhìn trên Console có thể không thay đổi đường truy cập của ứng dụng đó. Vì vậy, luôn bắt đầu từ kết nối thực tế trên client rồi đối chiếu về OCI.

## 3. Đọc các trường export option

Một entry mô tả chính sách cho một source, không phải danh sách tài khoản IAM.

| Trường API/JSON | Ý nghĩa | Ví dụ trong lab |
|---|---|---|
| `source` | Địa chỉ hoặc CIDR của NFS client | `10.40.10.11/32` |
| `requirePrivilegedSourcePort` | Có yêu cầu client dùng source port 1–1023 hay không | `true` |
| `access` | Quyền truy cập qua export | `READ_WRITE` hoặc `READ_ONLY` |
| `identitySquash` | Quy tắc ánh xạ UID/GID | `ROOT` |
| `anonymousUid` | UID nhận sau thao tác squash phù hợp | `65534` |
| `anonymousGid` | GID nhận sau thao tác squash phù hợp | `65534` |
| `allowedAuth` | Những kiểu xác thực NFS được phép | `["SYS"]` |
| `isAnonymousAccessAllowed` | Cho phép fallback danh tính anonymous trong tình huống tra cứu LDAP liên quan | `false` |

Kiểu dữ liệu phải đúng: boolean là `true`/`false`, UID/GID là số và `allowedAuth` là mảng. Những trường này thuộc cấu trúc `ClientOptions`. [Nguồn: OCI ClientOptions](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/filestorage/model/ClientOptions.html).

### Source mô tả máy kết nối

Với IPv4, `/32` chọn một địa chỉ, `/24` chọn một dải mạng. Source phải tương ứng địa chỉ mà dịch vụ nhận từ đường kết nối thực tế. Nếu truy cập từ on-premises hoặc qua thiết bị chuyển tiếp có đổi nguồn, đối chiếu routing và địa chỉ nguồn thực thay vì đoán.

SSH vào một VM qua Bastion rồi mount NFS từ VM đó thường tạo kết nối NFS từ VM; đó không phải kết nối NFS trực tiếp từ public IP của laptop. Nếu VM có nhiều VNIC, kiểm tra interface và source IP mà route tới mount target sử dụng.

Một `source` rộng như `0.0.0.0/0` không tự biến mount target thành địa chỉ public. Mount target không có IP định tuyến trực tiếp từ Internet, nhưng rule rộng vẫn cho phép mọi source có đường mạng và được các lớp khác chấp nhận. Khi tạo bằng CLI mà bỏ danh sách client options, một số mặc định IPv4 rất rộng; hãy khai báo và đọc lại chính sách tường minh. [Nguồn: OCI export create và mặc định client options](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/fs/export/create.html).

### Source port không phải destination port

`requirePrivilegedSourcePort: true` kiểm tra **cổng nguồn** của client. Nó không đổi cổng NFS đích và không có nghĩa chỉ process mang UID 0 mới được đọc file. Một NFS client do hệ điều hành quản lý có thể dùng kết nối nguồn đặc quyền để phục vụ yêu cầu của người dùng thường.

Trên Linux, mount option `resvport` đáp ứng yêu cầu dùng source port đặc quyền; `nosuid` giới hạn hiệu lực SUID/SGID của chương trình chạy từ mount đó. Hai lựa chọn xử lý các vấn đề khác nhau. [Nguồn: mount NFS từ UNIX-style instances](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/mountingunixstyleos.htm).

Source port đặc quyền là một điều kiện bổ sung, không phải phương thức xác thực mật mã danh tính người dùng. Không dùng nó thay cho quản trị an toàn các client được tin cậy.

## 4. Thứ tự entry và CIDR chồng lấn

OCI áp dụng **entry đầu tiên khớp Source IP** trong danh sách export options. Đây không phải cơ chế tự chọn CIDR cụ thể nhất. Nếu không có entry khớp, client không thấy export đó. [Nguồn: thứ tự áp dụng NFS export options](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/exportoptions.htm).

Xét một cấu hình minh họa khác với danh sách lab phía sau:

| Thứ tự | Source | Access |
|---:|---|---|
| 1 | `10.40.10.0/24` | `READ_ONLY` |
| 2 | `10.40.10.11/32` | `READ_WRITE` |

Client `10.40.10.11` khớp ngay entry 1 nên nhận quyền chỉ đọc. Entry 2 không được dùng để tăng quyền cho lần khớp đó.

Nếu chủ đích là một máy đọc/ghi và phần còn lại của subnet chỉ đọc, đặt ngoại lệ cụ thể trước:

| Thứ tự | Source | Access |
|---:|---|---|
| 1 | `10.40.10.11/32` | `READ_WRITE` |
| 2 | `10.40.10.0/24` | `READ_ONLY` |

Chính sách này cho cả những máy khác trong subnet quyền đọc. Nếu yêu cầu là chỉ đúng hai máy được truy cập, dùng hai entry `/32` riêng và không thêm entry cả subnet.

Không có thao tác “deny ở cuối để ghi đè allow ở đầu” theo cách suy luận trên. Trước khi cập nhật, viết ra danh sách source thử nghiệm và xác định entry đầu tiên mà từng source sẽ khớp.

## 5. Root squash và quyền file

`identitySquash` thay đổi danh tính được dùng khi kiểm tra quyền:

| Giá trị | Hệ quả |
|---|---|
| `NONE` | Không squash theo quy tắc này |
| `ROOT` | Ánh xạ danh tính root UID/GID 0 sang UID/GID anonymous được cấu hình |
| `ALL` | Ánh xạ mọi người dùng và nhóm sang danh tính cấu hình |

Ví dụ root squash với `anonymousUid=65534`, `anonymousGid=65534` không biến filesystem thành chỉ đọc. Danh tính sau ánh xạ vẫn có thể làm những việc được mode file/thư mục cho phép. Nếu một thư mục cho tất cả mọi người ghi, tài khoản bị squash có thể vẫn ghi được. [Nguồn: identity squash trong ClientOptions](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/filestorage/model/ClientOptions.html).

Với `AUTH_SYS`, cần đồng bộ và quản lý UID/GID giữa các client. Hai tên người dùng giống nhau nhưng khác UID không tự là cùng chủ sở hữu file; hai tên khác nhau nhưng cùng UID có thể được nhìn như cùng danh tính ở lớp kiểm tra quyền đó.

Root squash cũng không bảo vệ hoàn toàn khỏi một quản trị viên client có khả năng sử dụng UID không phải root được cấp quyền. Vì vậy, chọn source tin cậy và kiểm soát quản trị client là phần quan trọng của thiết kế `AUTH_SYS`.

Tùy chọn `isAnonymousAccessAllowed=false` không có nghĩa tắt root squash. Đây là trường liên quan tới việc cho phép dùng danh tính anonymous khi tra cứu người dùng LDAP trong cấu hình xác thực tương ứng; quy tắc squash vẫn là trường riêng. [Nguồn: Using Kerberos authentication](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/kerberos.htm).

Một phép kiểm tra thường gặp là `sudo touch` thất bại nhưng user ứng dụng ghi được. Nếu root đang bị squash còn thư mục thuộc UID của user ứng dụng, kết quả đó có thể đúng với thiết kế, không phải lỗi mạng.

## 6. Cấu hình mạng cho mount target

### Mô hình mạng của lab

| Thành phần | Địa chỉ minh họa |
|---|---|
| Subnet client | `10.40.10.0/24` |
| Subnet mount target | `10.40.20.0/24` |
| Mount target | `10.40.20.10` |
| Client A, đọc/ghi | `10.40.10.11` |
| Client B, chỉ đọc | `10.40.10.12` |
| Client C, bị export từ chối | `10.40.10.13` |

Tất cả địa chỉ phải thay theo môi trường thực. Dùng subnet riêng cho mount target và client giúp quản lý rõ phạm vi tài nguyên. Đường route phải cho hai bên liên lạc; nếu có peering, DRG, firewall hoặc ZPR, kiểm tra thêm điều kiện áp dụng ở các lớp đó.

Để tách phép thử export khỏi phép thử mạng, lab cho cả subnet client đi tới các cổng cần thiết. Khi đó client C có đường mạng nhưng vẫn phải bị export từ chối. Môi trường thật có thể giới hạn lớp mạng hơn nữa theo các client được phép.

### Các cổng cần cho NFSv3/RPC trong lab

Theo hướng dẫn OCI, cấu hình stateful ingress vào mount target và egress từ client với các destination port sau:

| Protocol | Destination ports tại mount target |
|---|---|
| TCP | `111`, `2048`, `2049`, `2050` |
| UDP | `111`, `2048` |

Mount target ingress dùng source `10.40.10.0/24`; client egress dùng destination `10.40.20.10/32`. Khi yêu cầu reserved source port, đặt source port range phù hợp `1–1023` và kiểm tra client sử dụng `resvport`. Traffic trả lời của kết nối stateful được theo dõi theo cơ chế stateful. [Nguồn: VCN security rules cho File Storage](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/securitylistsfilestorage.htm).

Chỉ mở TCP 2049 chưa chứng minh luồng mount, RPC và locking cần thiết đã hoạt động. Các cấu hình LDAP/Kerberos hoặc mã hóa có thêm đường kết nối cần thiết; bảng trên dành cho lab NFSv3 `AUTH_SYS`.

### NSG và security list

Gắn đúng NSG vào mount target và VNIC của client theo thiết kế. Security list áp dụng theo subnet; NSG áp dụng cho những VNIC/tài nguyên được gắn vào nhóm. Một NSG mới không tự bảo vệ mọi tài nguyên chỉ vì chúng ở cùng subnet.

Khi dùng cả NSG và security list, rà toàn bộ rule cho phép đang áp dụng. Một rule hẹp trong NSG không thu hẹp một rule rộng còn tồn tại ở security list. Nếu endpoint có ZPR security attribute thì còn phải đáp ứng ZPR policy tương ứng. [Nguồn: OCI security rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

Kiểm tra firewall trong guest và routing thực tế khi có timeout. Không tắt các lớp mạng hoặc mở mọi cổng để thay cho việc xác định cổng nào và chiều nào còn thiếu.

## 7. Chính sách export tường minh cho hai client

Yêu cầu lab:

- A `10.40.10.11` được đọc/ghi.
- B `10.40.10.12` chỉ được đọc.
- C `10.40.10.13` không có entry cho export này.
- A và B dùng privileged source port, `AUTH_SYS` và root squash.

Danh sách JSON dùng cho `--export-options`:

```json
[
  {
    "source": "10.40.10.11/32",
    "requirePrivilegedSourcePort": true,
    "access": "READ_WRITE",
    "identitySquash": "ROOT",
    "anonymousUid": 65534,
    "anonymousGid": 65534,
    "isAnonymousAccessAllowed": false,
    "allowedAuth": ["SYS"]
  },
  {
    "source": "10.40.10.12/32",
    "requirePrivilegedSourcePort": true,
    "access": "READ_ONLY",
    "identitySquash": "ROOT",
    "anonymousUid": 65534,
    "anonymousGid": 65534,
    "isAnonymousAccessAllowed": false,
    "allowedAuth": ["SYS"]
  }
]
```

Hai source không chồng lấn, giúp việc đọc lại và kiểm chứng đơn giản. Không thêm `0.0.0.0/0` phía sau để “dự phòng”, vì entry đó sẽ mở một đường truy cập cho các client khác.

### Cập nhật qua Console

Mở **Storage → File Storage → File Systems**, chọn đúng compartment và filesystem, rồi vào **Exports**. Chọn export bằng mount target và export path; mở **NFS client Export options** để sửa danh sách. Kiểm tra thứ tự, source và toàn bộ trường trước khi cập nhật.

Export path không sửa tại chỗ sau khi tạo; khi cần đổi path phải lập kế hoạch export khác và chuyển client. [Nguồn: editing an export](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/edit-export.htm).

### Cập nhật qua OCI CLI

Trong môi trường OCI CLI đã có xác thực và chọn đúng region/profile, đọc tài nguyên trước:

```bash
oci fs export get --export-id '<EXPORT_OCID>'
```

Ghi lại cấu hình trước và ETag nếu dùng kiểm soát cập nhật đồng thời. Lưu danh sách JSON đã chuẩn bị vào file `export-options.json` tại môi trường vận hành, rồi cập nhật:

```bash
oci fs export update \
  --export-id '<EXPORT_OCID>' \
  --export-options file://export-options.json \
  --if-match '<ETAG_DA_DOC>'
```

`--export-options` cập nhật **toàn bộ danh sách**, không tự nối một entry mới. `--if-match` giúp yêu cầu chỉ được áp dụng khi ETag vẫn khớp. Nếu có người sửa trước, đọc lại và hợp nhất theo mục tiêu thay vì tự ghi đè thay đổi đó. [Nguồn: OCI CLI export update](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/fs/export/update.html).

Sau cập nhật:

```bash
oci fs export get \
  --export-id '<EXPORT_OCID>' \
  --query 'data."export-options"'
```

Đối chiếu nội dung và thứ tự trả về với chính sách dự kiến. Thông báo API thành công là bằng chứng thay đổi cấu hình, chưa phải bằng chứng các client đã bị phân quyền đúng.

## 8. Chuẩn bị quyền dữ liệu cho phép thử

Để kiểm tra export, quyền UNIX phải cho phép thao tác cơ sở. Lab dùng một user ứng dụng có **UID 2000, primary GID 2000** trên A và B; client C có thể dùng cùng UID/GID để loại trừ khác biệt danh tính khi thử mount.

Trước khi tạo user, kiểm tra UID/GID và tên đang được sử dụng:

```bash
getent passwd 2000
getent group 2000
getent passwd fssapp
getent group fssapp
```

Chỉ với máy lab mới, khi các giá trị chưa được dùng và kế hoạch đã chọn UID/GID này, tạo:

```bash
sudo groupadd --gid 2000 fssapp
sudo useradd --uid 2000 --gid 2000 --create-home fssapp
id fssapp
```

Nếu máy đã có user phù hợp, dùng user đó thay vì sửa UID tài khoản đang chạy ứng dụng. Tên không bắt buộc giống nhau giữa các máy, nhưng số UID/GID dùng cho quyền phải được đối chiếu.

Người quản trị dữ liệu chuẩn bị trong filesystem lab một thư mục `/lab-data` thuộc `2000:2000`, mode `2770`. Thực hiện bằng đường quản trị đã có quyền tạo/chown thực sự, trước khi thu hẹp về chính sách hai client nói trên. Ví dụ dưới giả định đường quản trị đã mount đúng filesystem tại `/mnt/fss-admin`:

```bash
sudo mkdir -p /mnt/fss-admin/lab-data
sudo chown 2000:2000 /mnt/fss-admin/lab-data
sudo chmod 2770 /mnt/fss-admin/lab-data
ls -ldn /mnt/fss-admin/lab-data
```

Đây là bước cấp quyền dữ liệu, không phải lệnh thực hiện từ client root đã bị squash rồi kỳ vọng `sudo` sẽ vượt qua. Nếu phải có một export/entry bootstrap riêng để quản trị, giới hạn đúng nguồn quản trị, ghi lại mục đích và thu hồi trước khi kết luận bài lab hoàn tất.

Với mode `2770`, owner và group có quyền đọc/ghi/traverse; người khác không có quyền. Bit setgid giúp file/thư mục con kế thừa group của thư mục theo ngữ nghĩa UNIX tương ứng. Trong phép thử root squash, UID/GID anonymous không được là owner, group được cấp quyền hoặc có một đường quyền khác vào thư mục này.

## 9. Kiểm tra từ client được phép và bị từ chối

### Mount đúng export

Trên mỗi client Linux, cài NFS client phù hợp với image. Ví dụ Oracle Linux dùng `nfs-utils`; Ubuntu/Debian dùng `nfs-common`. Tạo mount point riêng và xác nhận chưa có mount khác tại đó.

```bash
sudo mkdir -p /mnt/fss-lab
sudo mount -t nfs \
  -o vers=3,proto=tcp,nosuid,resvport,sec=sys \
  10.40.20.10:/shared-lab /mnt/fss-lab

findmnt --mountpoint /mnt/fss-lab -o TARGET,SOURCE,FSTYPE,OPTIONS
```

Thay IP/path theo export thực tế. Dùng command mẫu của Console phù hợp authentication method nếu môi trường có cấu hình khác. Không dùng `soft` cùng mount read/write cho File Storage. [Nguồn: mount commands và mount options](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/mountingfilesystems.htm).

Lab dùng cùng cách yêu cầu mount để quyền chỉ đọc của B được kiểm tra từ phía server, thay vì tự đặt `ro` phía client rồi kết luận export đã chặn ghi.

### Client A: ứng dụng được ghi

Sau khi xác nhận `id fssapp` đúng UID/GID:

```bash
sudo -u fssapp sh -c 'printf "writer-check\n" > /mnt/fss-lab/lab-data/writer.txt'
sudo -u fssapp cat /mnt/fss-lab/lab-data/writer.txt
ls -ln /mnt/fss-lab/lab-data/writer.txt
```

Kỳ vọng tạo và đọc thành công. Quyền có hiệu lực là kết quả của export cho phép ghi và quyền thư mục cho danh tính đó ghi.

### Client B: đọc được, không tạo file mới được

```bash
sudo -u fssapp cat /mnt/fss-lab/lab-data/writer.txt
sudo -u fssapp touch /mnt/fss-lab/lab-data/reader-must-not-create.txt
```

Kỳ vọng đọc thành công và lệnh tạo file thất bại. Ghi lại lỗi thực tế và exit status. Nếu file đã được tạo, điều tra export/mount target đang dùng, source thực tế và entry áp dụng; không coi phép thử đạt chỉ vì client B có thể đọc.

Quyền mount hiển thị trong client không phải bằng chứng độc lập về quyền server cho phép. Hãy dùng kết quả thao tác được thiết kế với quyền UNIX đã biết.

### Client C: có đường mạng nhưng không được export cho phép

Từ client C, dùng đúng IP và export path để thử mount vào một mount point riêng chưa có mount. Kỳ vọng yêu cầu không được chấp nhận bởi export policy.

Để quy kết kết quả cho export options, phải có bằng chứng đường mạng và các dịch vụ cần thiết đã được cho phép tương ứng lab. Timeout mạng chỉ chứng minh kết nối chưa hoàn tất; nó không chứng minh export đã loại source C.

Không dùng một phiên mount cũ sang filesystem khác làm bằng chứng. Ghi source IP, destination mount target, export path và thời điểm thử.

### Root squash trên A

Trong điều kiện thư mục đã chuẩn bị như trên và root không có group phụ được cấp quyền, thử:

```bash
sudo touch /mnt/fss-lab/lab-data/root-must-not-create.txt
```

Kỳ vọng root bị ánh xạ sang danh tính anonymous và không tạo được file. Sau đó kiểm tra user `fssapp` vẫn thao tác được. Nếu root vẫn ghi được, xem mode/ownership, group membership, entry áp dụng và các đường truy cập khác; chỉ thấy UID 0 phía client chưa đủ kết luận server đã dùng UID 0.

Bảng ghi nhận tối thiểu:

| Client/danh tính | Đọc file mẫu | Tạo file | Điều được kiểm chứng |
|---|---|---|---|
| A, UID 2000 | Thành công | Thành công | RW cùng quyền UNIX phù hợp |
| B, UID 2000 | Thành công | Thất bại | Server giới hạn chỉ đọc |
| C | Không truy cập qua export | Không áp dụng | Source không được export cấp quyền |
| A, root bị squash | Theo quyền anonymous | Thất bại trong thư mục lab | Quy tắc squash và quyền thư mục phối hợp đúng |

## 10. Khi cần xác thực mạnh hoặc mã hóa

CIDR và `AUTH_SYS` phù hợp một số mạng client được quản lý chặt, nhưng không tự tạo bằng chứng mật mã về từng người dùng. OCI File Storage có các lựa chọn Kerberos:

| Giá trị | Chức năng chính |
|---|---|
| `KRB5` | Xác thực Kerberos |
| `KRB5I` | Xác thực và bảo vệ tính toàn vẹn dữ liệu truyền |
| `KRB5P` | Thêm bảo mật nội dung dữ liệu truyền |

Dùng Kerberos cần cấu hình mount target, ánh xạ danh tính, LDAP và client tương thích; không chỉ thay `["SYS"]` bằng một chuỗi trong JSON. [Nguồn: OCI Kerberos authentication](https://docs.oracle.com/en-us/iaas/Content/File/Tasks/kerberos.htm).

Nếu yêu cầu bắt buộc đi qua Kerberos, rà việc vẫn cho phép `SYS` trong cùng chính sách hoặc qua export khác. Một đường `SYS` còn mở có thể làm yêu cầu bắt buộc Kerberos không còn được thực thi như dự kiến. [Nguồn: lưu ý bảo mật khi cấu hình File Storage với Active Directory](https://docs.oracle.com/en/solutions/configure-file-storage-for-active-directory/considerations-security.html).

Mã hóa dữ liệu lưu trữ và mã hóa đường truyền là hai thuộc tính khác nhau. Việc chọn source hẹp, root squash hoặc mount `nosuid` không tự bật TLS. OCI còn có cơ chế mã hóa đường truyền bằng công cụ client tương ứng; chọn theo yêu cầu và kiểm tra cấu hình thực tế. [Nguồn: File Storage security và in-transit encryption](https://docs.oracle.com/en-us/iaas/Content/File/Concepts/securitylayers.htm).

## 11. Cập nhật, thu hồi và kiểm tra các đường truy cập khác

Trước khi thay đổi source hoặc access của export đang dùng, xác định client và ứng dụng bị ảnh hưởng. Việc mất quyền giữa một tác vụ ghi có thể gây lỗi I/O cho ứng dụng, nên chọn thời điểm và cách dừng công việc phù hợp.

Quy trình vận hành đề xuất:

1. Ghi cấu hình hiện tại và đường truy cập của các client.
2. Xác định danh sách hoàn chỉnh sau thay đổi, gồm thứ tự entry.
3. Cập nhật bằng cơ chế kiểm soát thay đổi phù hợp.
4. Đọc lại chính sách từ OCI.
5. Thử các thao tác được phép và bị từ chối từ đúng client/danh tính.
6. Rà những export/mount target khác của cùng filesystem.
7. Thu hồi đường bootstrap và ghi kết quả bàn giao.

Với CLI, `--export-options '[]'` làm export đó không nhìn thấy đối với các client; bỏ hẳn tham số `--export-options` khi update giữ nguyên danh sách. Hai hành động khác nhau. [Nguồn: OCI export update](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/fs/export/update.html).

Đóng một export không chứng minh toàn bộ filesystem đã bị thu hồi truy cập nếu còn export khác cho phép source đó. Tương tự, xóa một rule trong NSG chưa đủ nếu security list còn cấp đường mạng rộng hơn. Đối chiếu toàn bộ đường truy cập cần thu hồi.

Không coi thay đổi chính sách là cách xóa dữ liệu mà client đã đọc hoặc sao chép trước đó. Khi cần kết luận về phiên đang hoạt động, ghi nhận riêng việc dừng ứng dụng, unmount bình thường, tạo kết nối kiểm tra mới và kết quả sau thay đổi; không mặc định phiên có sẵn phản ánh đầy đủ một phép mount mới.

## 12. Tìm lỗi và tiêu chí hoàn thành

| Hiện tượng | Lớp cần xem trước | Kiểm tra cụ thể |
|---|---|---|
| Mount timeout | Mạng | Route, IP đích, NSG/security list, cổng RPC/NFS, firewall và ZPR nếu có |
| Mount bị từ chối | Export/xác thực | Source IP, path, entry đầu tiên, source port và `sec` |
| Mount được nhưng user không ghi được | Quyền file hoặc access | `READ_ONLY`, UID/GID, ownership, mode và squash |
| Root không ghi nhưng user ứng dụng ghi được | Squash | Đối chiếu UID/GID anonymous và quyền thư mục |
| Máy cần RW chỉ có RO | Thứ tự entry | CIDR rộng phía trên có khớp trước ngoại lệ `/32` không? |
| Client ngoài danh sách vẫn truy cập | Export khác hoặc rule rộng | Kiểm tra source thực và mọi export/mount target liên quan |
| Sửa một entry làm client khác mất quyền | Cách update | Danh sách đã bị thay thế và thiếu entry cần giữ? |
| Kerberos client lỗi nhưng SYS dùng được | Authentication | Kiểm tra kiểu được phép, cấu hình Kerberos và đường fallback |
| Kiểm tra ghi báo thành công nhưng dữ liệu ở local | Mount point | Xác minh `findmnt --mountpoint` trước khi ghi |

Khi đọc log và chia sẻ bằng chứng, giữ OCID, IP, path, danh tính số và thời điểm cần thiết theo quy định của nhóm; không đưa secret hoặc credential vào tài liệu kiểm tra.

Bài thực hành hoàn tất khi có bằng chứng cho các yêu cầu sau:

- Đúng filesystem, export, export path và mount target đã được nhận diện.
- Network rules đủ cho luồng cần thiết và chỉ có phạm vi nguồn dự kiến.
- Export options có danh sách đầy đủ, kiểu dữ liệu đúng và thứ tự đã kiểm chứng.
- A đọc/ghi được, B đọc được nhưng không ghi được, C không truy cập qua export.
- Root squash được thử trong thư mục có quyền đã biết, tách biệt với phép thử user ứng dụng.
- Không còn đường bootstrap hoặc export khác làm trái mục tiêu phân quyền.
- Có người chịu trách nhiệm theo dõi cấu hình; tài nguyên lab được giữ hoặc thu hồi theo mục đích và chi phí đã thống nhất.

Một chính sách truy cập File Storage có thể kiểm chứng phải nối được **source mạng → export áp dụng → danh tính hiệu lực → thao tác trên dữ liệu**. Theo dõi đầy đủ chuỗi này giúp giải thích lỗi và tránh kết luận quyền đúng chỉ từ một lần mount thành công.
