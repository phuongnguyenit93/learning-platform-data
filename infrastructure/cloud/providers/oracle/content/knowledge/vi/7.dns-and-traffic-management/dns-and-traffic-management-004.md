# Quản lý tên miền, TTL và chuyển đổi DNS an toàn

## 1. Mục tiêu và bối cảnh

Trong chương **DNS và điều phối truy cập** của module Oracle Cloud Infrastructure (OCI), thay đổi DNS là một phần của quá trình vận hành dịch vụ: chuyển website sang load balancer mới, thay địa chỉ Compute, chuyển DNS hosting sang OCI hoặc chuẩn bị chuyển lưu lượng giữa các region.

Một lần sửa bản ghi thành công trên Console chưa có nghĩa mọi client đã dùng kết quả mới. Chuyển đổi an toàn đòi hỏi quản lý quyền sở hữu tên miền, dữ liệu authoritative, delegation, cache, sức khỏe ứng dụng và thời gian giữ hệ thống cũ.

Sau bài học, bạn có thể:

- Phân loại thay đổi để xác định đúng hệ thống và người chịu trách nhiệm.
- Lập hồ sơ tên miền, TTL và các phụ thuộc DNS cần bảo toàn.
- Tính cửa sổ chuẩn bị cho việc hạ TTL, theo dõi chuyển đổi và quay lui.
- Chuyển endpoint hoặc DNS hosting sang OCI theo từng giai đoạn.
- Kiểm chứng authoritative, delegation, recursive resolver và ứng dụng.
- Chọn điều kiện thu hồi tài nguyên cũ dựa trên quan sát và yêu cầu vận hành.

Các tên `example.com`, `lab.example.com` và địa chỉ `203.0.113.x`, `2001:db8:...` trong bài chỉ dùng minh họa. Khi thực hành, thay bằng tên thuộc quyền quản lý và endpoint thật. Các mốc thời gian, TTL và ngưỡng nghiệm thu là ví dụ, cần điều chỉnh theo hệ thống.

## 2. Phân biệt các loại chuyển đổi

Trước khi sửa bất kỳ cấu hình nào, hãy viết rõ mục tiêu: thay nơi đăng ký tên miền, thay nơi trả lời DNS hay thay nơi phục vụ ứng dụng.

| Thay đổi | Thành phần chính bị tác động | Điều không tự diễn ra |
| --- | --- | --- |
| Đổi IP hoặc hostname đích của dịch vụ | A, AAAA, CNAME hoặc cơ chế endpoint tương ứng | Không tự đổi registrar hay nameserver |
| Chuyển DNS hosting sang OCI | Zone đích, dữ liệu DNS và delegation NS | Không tự chuyển đăng ký tên miền |
| Chuyển registrar | Tài khoản và quy trình quản lý đăng ký tên miền | Không bắt buộc phải đổi DNS hosting |
| Đổi tên miền người dùng truy cập | DNS, chứng thư, ứng dụng, URL và các tích hợp | Không được giải quyết chỉ bằng CNAME |
| Chuyển dịch vụ sang region khác | Endpoint, dữ liệu, cấu hình ứng dụng và DNS liên quan | DNS không tự sao chép database hoặc storage |

OCI DNS không phải registrar. Muốn delegation của một domain đăng ký trỏ đến OCI, người quản lý phải cập nhật nameserver qua registrar; với child zone, cập nhật NS ở authoritative zone cha tương ứng. [Oracle: Delegating a Public DNS Zone](https://docs.oracle.com/en-us/iaas/Content/DNS/Concepts/gettingstarted_topic-Delegating_Your_Zone.htm)

Ví dụ, chuyển `api.lab.example.com` từ load balancer cũ sang load balancer mới thường chỉ cần đổi dữ liệu đích. Không cần thay delegation của toàn bộ `example.com`.

Ngược lại, nếu chuyển hosting của `lab.example.com` từ nhà cung cấp khác sang OCI nhưng vẫn dùng cùng endpoint ứng dụng, nên giữ dữ liệu ứng dụng giống nhau trong giai đoạn chuyển NS. Tách các thay đổi này giúp xác định nguyên nhân và quay lui rõ hơn.

## 3. Quản lý tên miền như một tài nguyên vận hành

### 3.1. Hồ sơ tối thiểu cho mỗi domain hoặc zone

| Thông tin | Mục đích |
| --- | --- |
| Tên miền, zone cha và các child zone | Xác định ranh giới quản lý và delegation |
| Registrar, chủ tài khoản, kênh khôi phục | Đảm bảo tổ chức có thể duy trì và lấy lại quyền quản lý |
| Ngày hết hạn, người chịu trách nhiệm gia hạn | Tránh gián đoạn vì đăng ký hết hạn |
| Nhà cung cấp DNS hiện tại, nameserver | Biết nơi thực sự trả lời authoritative |
| OCI compartment, OCID và scope của zone | Tránh sửa nhầm tài nguyên trùng tên |
| Trạng thái DNSSEC, nơi quản lý DS | Lập kế hoạch cho chuỗi tin cậy khi chuyển NS |
| Nguồn cấu hình và người được phép sửa | Tránh ghi đè giữa Console và pipeline |
| Dịch vụ và nhóm sử dụng tên miền | Đánh giá ảnh hưởng ngoài website chính |
| Phương án quay lui, thời gian giữ hệ thống cũ | Có đường phục hồi đã chuẩn bị |

Tài khoản registrar nên thuộc quyền kiểm soát của tổ chức, có phương thức xác thực và khôi phục phù hợp. Kênh liên hệ khẩn cấp cần có phương án vẫn dùng được khi chính domain đang gặp sự cố.

Dùng cơ chế nhắc gia hạn, cảnh báo và phân công cụ thể. Bật tự động gia hạn không thay thế việc kiểm tra phương thức thanh toán và trạng thái tên miền. Quy tắc hết hạn, khôi phục hoặc chuyển registrar phụ thuộc registrar và loại tên miền; kiểm tra quy trình đang áp dụng thay vì dùng một thời hạn chung.

### 3.2. Quyền tại OCI và quyền tại registrar

Một người được phép sửa RRset trong OCI chưa chắc được phép thay NS hoặc DS tại registrar. Kế hoạch chuyển đổi phải xác định ai thực hiện từng phần và ai có quyền quay lui.

Trong OCI, tách nhu cầu đọc zone, chỉnh bản ghi và quản lý vòng đời zone. Có thể giới hạn theo compartment, zone, tên miền hoặc type bản ghi. Không cấp toàn quyền DNS trên tenancy chỉ vì công việc cần sửa một A RRset. [Oracle: Details for the DNS Service](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/dnspolicyreference.htm)

Trước cửa sổ chuyển đổi, xác nhận quyền bằng các thao tác đọc và kiểm tra phạm vi. Đừng đợi tới thời điểm đổi NS mới phát hiện người phụ trách không có quyền truy cập zone cha.

## 4. TTL thực sự kiểm soát điều gì?

### 4.1. TTL gắn với dữ liệu được cache

Giả sử bản ghi hiện tại là:

```text
api.lab.example.com.  3600  IN  A  203.0.113.10
```

Resolver nhận bản ghi lúc 09:00 có thể sử dụng kết quả đã cache trong thời gian tương ứng với TTL. Nếu authoritative đổi IP lúc 09:10, nó không gửi lệnh thu hồi tới mọi cache đã nhận kết quả cũ.

Nếu đồng thời hạ TTL từ 3600 xuống 300 lúc 09:10, cache đã có dữ liệu từ trước không bị sửa ngược về 300 giây.

Vì vậy, quy trình chuẩn bị phải gồm hai thay đổi khác nhau:

1. Hạ TTL và giữ nguyên RDATA.
2. Chờ cửa sổ TTL cũ theo kế hoạch, sau đó mới đổi RDATA.

TTL thấp giúp các lần truy vấn mới làm mới dữ liệu thường xuyên hơn. Nó không bảo đảm mọi client trên Internet chuyển địa chỉ trong đúng một số giây cố định.

### 4.2. Không có một TTL chung cho toàn bộ hostname

Một đường phân giải có thể đi qua nhiều dữ liệu:

```text
www.lab.example.com.  CNAME  api.lab.example.com.
api.lab.example.com.  A      203.0.113.10
api.lab.example.com.  AAAA   2001:db8:42::10
```

CNAME, A và AAAA là các RRset khác nhau, có thời gian cache riêng. Hạ TTL của CNAME không tự hạ TTL A của target; đổi A không tự đổi AAAA.

Khi chuyển DNS hosting, còn phải xem NS delegation ở zone cha và NS ở apex. Nếu zone có DNSSEC, DS và DNSKEY tạo thêm các phụ thuộc về thời gian. TTL của A là 300 giây không có nghĩa cache NS hay DS cũng chỉ tồn tại 300 giây.

Một bảng chuẩn bị nên ghi rõ:

| Dữ liệu | Giá trị cũ | Giá trị dự kiến | TTL cũ | Ai có quyền sửa |
| --- | --- | --- | --- | --- |
| A của API | IP cũ | IP mới | Đọc từ cấu hình hiện hành | Nhóm DNS OCI |
| AAAA của API | IPv6 cũ hoặc chưa có | Phương án IPv6 tương ứng | Kiểm tra riêng | Nhóm DNS OCI |
| CNAME của website | Target hiện tại | Giữ hoặc đổi có chủ đích | Kiểm tra riêng | Chủ zone |
| NS delegation | NS cũ | NS OCI được cấp | Đọc từ zone cha | Chủ zone cha/registrar |
| DS nếu có | Digest hiện tại | Theo kế hoạch DNSSEC | Kiểm tra tại cha | Chủ zone cha/registrar |

Đọc cấu hình authoritative để biết TTL đã công bố. TTL nhìn qua recursive resolver thường là thời gian còn lại của một bản sao đang cache, không phải giá trị cấu hình ban đầu.

### 4.3. Cache âm

Nếu client hỏi một tên chưa tồn tại, kết quả NXDOMAIN có thể được cache. Nếu tên có tồn tại nhưng thiếu type được hỏi, có thể nhận NODATA. Thêm bản ghi sau đó không tự xóa các cache âm.

Theo quy tắc negative caching, thời hạn liên quan giá trị nhỏ hơn giữa TTL của SOA và trường SOA MINIMUM trong phản hồi phù hợp. Đây không phải TTL của A vừa được tạo. [RFC 2308: Negative Caching of DNS Queries](https://www.rfc-editor.org/rfc/rfc2308.txt)

Do đó, nên chuẩn bị hostname mới trước khi phát hành cấu hình client. Tránh phát hành ứng dụng trỏ tới một tên chưa tạo rồi kỳ vọng sửa DNS sau đó sẽ khôi phục ngay tất cả client.

### 4.4. Cache ứng dụng và dữ liệu cũ

Ngoài DNS resolver còn có cache trong OS, runtime, trình duyệt hoặc thư viện HTTP. Một số resolver có cơ chế serve-stale để tiếp tục trả dữ liệu cũ khi không làm mới được từ authoritative, nhằm cải thiện khả năng chịu lỗi. Không dùng TTL làm cam kết tuyệt đối về thời điểm mọi dữ liệu cũ biến mất. [RFC 8767: Serving Stale Data to Improve DNS Resiliency](https://datatracker.ietf.org/doc/html/rfc8767)

Với Java, `InetAddress` có cache cho kết quả phân giải thành công và thất bại. Các security property như `networkaddress.cache.ttl` và `networkaddress.cache.negative.ttl` ảnh hưởng hành vi; cần kiểm tra JDK và cấu hình runtime thực tế. Không mặc định TTL của JVM luôn bằng TTL trả về từ authoritative DNS. [Java: InetAddress Caching](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/InetAddress.html)

Việc thay DNS cũng không chuyển một TCP connection, WebSocket hoặc phiên kết nối database đang mở sang IP mới. Client chỉ sử dụng kết quả mới khi nó thực sự phân giải lại và tạo kết nối phù hợp.

## 5. Kiểm kê trước khi chuyển đổi

### 5.1. Kiểm kê toàn bộ dữ liệu phục vụ dịch vụ

Không chỉ ghi lại A của website. Cần rà:

- A, AAAA, CNAME của frontend và API.
- MX và các TXT liên quan email như SPF, DKIM, DMARC.
- TXT xác minh quyền sở hữu hoặc phục vụ cấp chứng thư.
- CAA và các chính sách ảnh hưởng cấp chứng thư.
- Wildcard, SRV hoặc các type khác mà hệ thống sử dụng.
- NS delegation cho các child zone.
- DS, trạng thái ký và phụ thuộc DNSSEC.
- Bản ghi do dịch vụ tự động quản lý hoặc có steering policy attachment.

OCI có các kiểu dữ liệu và cơ chế như ALIAS; khi chuyển nhà cung cấp, phải đối chiếu khả năng và ngữ nghĩa. Không sao chép một tính năng riêng của nhà cung cấp thành bản ghi chuẩn khác chỉ vì nhìn giống hostname. [Oracle: Managing Resource Records](https://docs.oracle.com/en-us/iaas/Content/DNS/Reference/supporteddnsresource.htm)

Danh sách query DNS không phải bản kiểm kê đầy đủ. Truy vấn `ANY` không thay thế được việc lấy danh sách cấu hình zone; wildcard cũng không cho biết mọi tên đang sử dụng.

### 5.2. Kiểm kê phụ thuộc ngoài DNS

Xác nhận endpoint mới đã có:

| Thành phần | Điều cần kiểm tra |
| --- | --- |
| TLS | Chứng thư hợp lệ cho hostname người dùng tiếp tục truy cập |
| Listener và mạng | Cổng, route, NSG, firewall OS và backend hoạt động |
| Ứng dụng | Virtual host, callback URL, cookie, CORS và allowlist phù hợp |
| Dữ liệu | Database và storage có dữ liệu nhất quán theo yêu cầu |
| Tích hợp | Đối tác, webhook và hệ thống phụ trợ chấp nhận endpoint mới |
| Giám sát | Phân biệt được đích cũ/đích mới và lỗi nghiệp vụ |
| Quay lui | Đích cũ vẫn có khả năng phục vụ, bao gồm trạng thái dữ liệu |

Nếu đổi region của ứng dụng OCI, DNS không sao chép dữ liệu Oracle Database hoặc Object Storage. Phương án dữ liệu, thời điểm cho phép ghi và khả năng quay lui phải được chuẩn bị trước khi đổi hướng client.

Giữ hai frontend sống đồng thời không đồng nghĩa có thể để hai bản sao database nhận ghi độc lập. Giai đoạn chuyển tiếp phải phù hợp với kiến trúc dữ liệu thực tế.

## 6. Kịch bản A: chuyển endpoint, giữ DNS hosting

### 6.1. Phạm vi ví dụ

Giả sử public zone đang do OCI quản lý:

```text
Trước chuyển:
api.lab.example.com.  3600  IN  A  203.0.113.10

Sau chuyển:
api.lab.example.com.   300  IN  A  203.0.113.20
```

Đích mới có cùng chức năng nghiệp vụ và chứng thư phù hợp. Nameserver không đổi. Địa chỉ trên là dữ liệu tài liệu; phải thay bằng IP thật khi làm lab.

### 6.2. Lịch chuyển đổi mẫu

| Thời điểm | Việc thực hiện | Điều kiện tiếp tục |
| --- | --- | --- |
| Trước ngày chuyển | Kiểm kê, chuẩn bị endpoint mới và kế hoạch dữ liệu | Dịch vụ mới vượt kiểm thử độc lập |
| 08:00 ngày thứ nhất | Giữ IP cũ, hạ TTL từ 3600 xuống 300 | Authoritative đã phục vụ TTL thấp |
| Sau ít nhất cửa sổ TTL cũ kể từ xác nhận | Cho phép bước đổi IP theo kế hoạch | Đã đánh giá thêm cache client và phụ thuộc |
| Thời điểm chuyển đã chọn | Đổi A sang IP mới | Request và readback đúng RRset |
| Giai đoạn chuyển tiếp | Giữ đích cũ, quan sát cả hai | Lỗi, độ trễ và dữ liệu nằm trong ngưỡng |
| Sau khi ổn định | Cân nhắc nâng TTL và thu hồi tài nguyên cũ | Đạt tiêu chí kết thúc đã định |

Không lấy mốc bấm Save làm mốc bắt đầu chờ nếu thay đổi chưa được publish hoặc authoritative chưa phục vụ TTL mới.

Trong mô hình cache thông thường của những RRset đã xác định, cửa sổ chuẩn bị ít nhất phải xét TTL cũ lớn nhất còn liên quan. Đây là điều kiện lập kế hoạch, không phải chứng minh mọi client đã đổi sau đúng thời gian đó.

### 6.3. Thực hiện thay đổi trong OCI

Trên Console, mở đúng public zone theo OCID, chọn RRset của API và chỉ sửa TTL trong bước chuẩn bị. Lưu, kiểm tra phần thay đổi rồi Publish Changes.

Tới cửa sổ chuyển, sửa RDATA bằng tập đích mong muốn, publish và đọc lại. Trong luồng Console, dữ liệu đang staged chưa phải dữ liệu đã phục vụ cho truy vấn. [Oracle: Changing DNS Zone Records](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/record-edit.htm)

Nếu dùng API/CLI, lưu ý thao tác cập nhật RRset là thay thế toàn bộ tập bản ghi tại owner/type đó. Ví dụ dưới đây chỉ dành cho A RRset của lab đã được xác nhận có đúng một địa chỉ cần thay:

```bash
DNS_ZONE_OCID='REPLACE_WITH_OCI_PUBLIC_ZONE_OCID'

oci dns record rrset update \
  --zone-name-or-id "$DNS_ZONE_OCID" \
  --domain 'api.lab.example.com' \
  --rtype A \
  --scope GLOBAL \
  --items '[
    {"domain":"api.lab.example.com","rtype":"A","ttl":300,"rdata":"203.0.113.20"}
  ]'
```

Nếu RRset có nhiều địa chỉ cần giữ, request phải chứa đầy đủ các giá trị đó. Với tự động hóa có nhiều người cùng sửa, sử dụng điều kiện phiên bản/ETag hợp lệ qua `--if-match` khi phù hợp, xử lý xung đột bằng cách đọc lại. [Oracle CLI: Update RRset](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/dns/record/rrset/update.html)

Không mặc định việc sửa A và AAAA là một giao dịch nguyên tử chung. Nếu cả hai cần đổi, phải chuẩn bị endpoint và thứ tự sao cho các trạng thái trung gian vẫn chấp nhận được.

## 7. Kịch bản B: chuyển DNS hosting sang OCI

Kịch bản này thay nơi trả lời authoritative. Mục tiêu ban đầu là giữ nguyên hành vi của ứng dụng trong khi thay DNS hosting.

### 7.1. Chuẩn bị zone đích trước delegation

1. Lấy bản kiểm kê đầy đủ từ nhà cung cấp cũ.
2. Tạo primary public zone đúng tên trong OCI, ở compartment được giao.
3. Nhập hoặc tạo lại các bản ghi ứng dụng và delegation con.
4. Xử lý các khác biệt về ALIAS, wildcard, steering và bản ghi được quản lý.
5. Giữ SOA và NS hệ thống của zone OCI theo thiết kế của dịch vụ; không thay chúng bằng NS của nhà cung cấp cũ.
6. Ghi nhận toàn bộ nameserver OCI cấp cho chính zone đích.
7. Truy vấn trực tiếp từng nameserver mới và đối chiếu dữ liệu.

Hai nhà cung cấp có thể dùng SOA serial, NS và dữ liệu ký khác nhau. Mục tiêu là kiểm chứng tính tương đương của dữ liệu phục vụ và đường delegation, không bắt mọi bản ghi quản lý phải giống từng byte.

Đừng lấy việc tạo được zone trong OCI làm bằng chứng Internet đã dùng zone đó.

### 7.2. Giữ dữ liệu cũ và mới nhất quán

Trong thời gian chuyển NS, các resolver khác nhau có thể còn hỏi nhà cung cấp cũ hoặc đã hỏi OCI. Hai phía cần trả dữ liệu ứng dụng tương đương.

Áp dụng một trong hai cách có chủ đích:

- Tạm dừng các thay đổi DNS không cần thiết trong cửa sổ chuyển.
- Nếu vẫn phải thay đổi, cập nhật có kiểm soát ở cả hai phía và xác minh đồng bộ.

Chỉ định một người hoặc một quy trình chịu trách nhiệm điều phối. Không để hai pipeline độc lập tự sửa cấu hình theo hai nguồn dữ liệu mâu thuẫn.

Không tự ghép NS cũ và NS mới vào một danh sách như cách chia 50/50 lưu lượng. Resolver không coi NS là cơ chế phân phối theo tỷ lệ; mọi nameserver được delegation phải có khả năng trả lời đúng.

### 7.3. Đổi delegation

Với domain đăng ký như `example.com`, thay nameserver theo quy trình registrar. Với child zone `lab.example.com`, thay NS delegation tại zone cha `example.com`.

Sử dụng đúng bộ nameserver OCI được cấp. Việc sửa NS chỉ ở apex của zone con không thay cho delegation ở cha.

NS có thể được cache lâu. Oracle lưu ý việc nhận biết bộ nameserver mới qua resolver có thể mất 24–48 giờ trong một số trường hợp; không dùng khoảng này như thời hạn cố định cho mọi domain. Lập kế hoạch theo TTL, trạng thái registrar/zone cha và quan sát thực tế. [Oracle: Delegating a Public DNS Zone](https://docs.oracle.com/en-us/iaas/Content/DNS/Concepts/gettingstarted_topic-Delegating_Your_Zone.htm)

### 7.4. Tiếp tục giữ nhà cung cấp cũ

Sau khi đổi NS, giữ zone cũ còn hoạt động trong cửa sổ chuyển tiếp đã tính. Nếu hủy dịch vụ cũ ngay, resolver còn cache delegation cũ có thể không tìm được câu trả lời dù OCI hoàn toàn khỏe.

Tiêu chí kết thúc phải bao gồm kiểm tra delegation, tính nhất quán từ các resolver phù hợp và không còn phụ thuộc đã biết vào dịch vụ cũ. Nếu không có log truy vấn đầy đủ ở phía cũ, dùng thời gian giữ có cơ sở và các phép thử bổ sung; không suy ra không còn client chỉ từ một truy vấn trên laptop.

Chỉ đổi IP ứng dụng sau khi việc chuyển DNS hosting đã ổn định, trừ khi yêu cầu buộc phải gộp hai thay đổi và đã đánh giá mọi trạng thái trung gian.

## 8. DNSSEC là một nhánh kế hoạch riêng

DNSSEC thêm xác thực dữ liệu DNS bằng chữ ký và chuỗi tin cậy. Nó không mã hóa nội dung câu trả lời và không thay thế TLS.

Khi zone có DNSSEC, DS ở cha phải phù hợp với khóa của zone con. Đổi sang nameserver có khóa khác trong khi DS cũ vẫn có hiệu lực có thể khiến validating resolver trả SERVFAIL.

Tài liệu OCI hướng dẫn chuyển một zone đã ký sang OCI bằng việc xử lý tắt DNSSEC ở phía cũ trước, sao chép dữ liệu rồi thiết lập lại DNSSEC trên OCI. Không diễn giải việc tắt này thành chỉ bấm ngừng ký ngay lập tức. [Oracle: DNSSEC](https://docs.oracle.com/en-us/iaas/Content/DNS/Concepts/dnssec.htm)

Các nguyên tắc bắt buộc cho kế hoạch tương ứng:

- Kiểm kê DS tại cha, DNSKEY tại con và TTL liên quan.
- Nếu dùng phương án chuyển qua trạng thái không ký, gỡ DS theo quy trình và chờ cửa sổ TTL DS trước khi ngừng khả năng phục vụ chữ ký mà các validator còn cần.
- Với zone có delegation con, xem xét các DS và chuỗi tin cậy bên dưới, không áp dụng máy móc quy trình cho một zone đơn lẻ.
- Trên OCI, đợi cấu hình ký sẵn sàng, thiết lập DS đúng tại cha và hoàn tất các bước quản lý khóa theo hướng dẫn.
- Xác nhận bằng resolver có validation và công cụ phù hợp trước khi kết thúc.

Quy trình tắt DNSSEC của OCI nêu rõ phải thực hiện việc gỡ DS và chờ TTL liên quan theo thứ tự trước khi tắt hoặc xóa zone. Với nhà cung cấp nguồn khác, đối chiếu quy trình chính thức của nguồn. [Oracle: Disabling DNSSEC on a Zone](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/dnssec-disable.htm)

Nếu yêu cầu bảo mật không cho phép khoảng không được xác thực, cần thiết kế một phương án chuyển có hỗ trợ từ các nhà cung cấp và được kiểm chứng riêng. Không giả định xuất/nhập zone file cũng chuyển được toàn bộ trạng thái khóa và chuỗi tin cậy.

Bài lab cơ bản có thể dùng child zone chưa bật DNSSEC để học chuyển NS. Không áp dụng trực tiếp chuỗi bước đó cho zone đang có DS.

## 9. Bộ lệnh kiểm chứng chuyển đổi

Các ví dụ dùng Bash và công cụ `dig`, `curl`. Thay placeholder và địa chỉ tài liệu bằng thông tin thật. Chọn nguồn kiểm tra được phép truy vấn theo chính sách mạng.

### 9.1. Authoritative cũ và mới

```bash
DNS_OLD_NS='REPLACE_WITH_OLD_AUTHORITATIVE_NAMESERVER'
DNS_NEW_NS='REPLACE_WITH_ASSIGNED_OCI_NAMESERVER'

dig @"$DNS_OLD_NS" api.lab.example.com. A +norecurse
dig @"$DNS_NEW_NS" api.lab.example.com. A +norecurse

dig @"$DNS_NEW_NS" api.lab.example.com. AAAA +norecurse
dig @"$DNS_NEW_NS" lab.example.com. SOA +norecurse
dig @"$DNS_NEW_NS" lab.example.com. NS +norecurse
```

Lặp lại phép thử trên từng nameserver được cấp khi cần. Đọc status, Answer section, TTL và cờ `aa`; không chỉ nhìn IP.

Với trường hợp chỉ đổi endpoint trong OCI, authoritative cũ và mới là cùng dịch vụ, khác nhau ở dữ liệu trước và sau. Không cần dựng một nameserver cũ chỉ để chạy đủ ví dụ.

### 9.2. Delegation và recursive resolver

```bash
dig +trace lab.example.com. NS
dig api.lab.example.com. A
dig api.lab.example.com. AAAA

DNS_RECURSOR='REPLACE_WITH_SELECTED_RECURSIVE_RESOLVER_IP'
dig @"$DNS_RECURSOR" api.lab.example.com. A
```

Truy vấn trực tiếp authoritative kiểm tra dữ liệu ở nguồn. `+trace` giúp xem delegation; truy vấn thường phản ánh đường resolver được cấu hình cho máy. Mỗi phép thử trả lời một câu hỏi khác nhau. [Oracle: Testing DNS Using dig](https://docs.oracle.com/en-us/iaas/Content/DNS/Tasks/testingdnsusingdig.htm)

Nếu mạng chặn DNS trực tiếp ra Internet, trace có thể timeout dù client vẫn dùng được resolver doanh nghiệp. Nếu có private view cùng tên, phải xác định đang hỏi namespace nào.

Với DNSSEC, có thể quan sát dữ liệu liên quan:

```bash
dig +trace lab.example.com. DS
dig @"$DNS_NEW_NS" lab.example.com. DNSKEY +dnssec +norecurse
dig @"$DNS_RECURSOR" api.lab.example.com. A +dnssec
```

`+dnssec` yêu cầu dữ liệu DNSSEC trong phản hồi, không tự biến `dig` thành công cụ xác thực đầy đủ mọi chữ ký. Việc không thấy cờ AD cũng không tự chứng minh chữ ký sai; cần hiểu resolver, kênh kiểm thử và chính sách validation đang dùng.

### 9.3. Thử đích mới trước khi đổi DNS

```bash
curl --noproxy '*' \
  --resolve 'api.lab.example.com:443:203.0.113.20' \
  --connect-timeout 5 --max-time 15 \
  https://api.lab.example.com/health
```

Lệnh ép địa chỉ kết nối nhưng giữ hostname phục vụ HTTP Host và TLS SNI. Cần chứng thư hợp lệ cho hostname đó; không thêm `-k` để bỏ qua lỗi chứng thư.

Sau chuyển, thử theo đường DNS thật:

```bash
curl --noproxy '*' --connect-timeout 5 --max-time 15 \
  -w '\nremote=%{remote_ip} status=%{http_code} total=%{time_total}\n' \
  https://api.lab.example.com/health
```

Nếu có cả A và AAAA, thử riêng bằng `-4` và `-6` từ máy có kết nối tương ứng. `--noproxy '*'` phục vụ phép thử trực tiếp; nếu hệ thống bắt buộc qua proxy, bổ sung phép thử đường proxy thực tế.

HTTP 200 tại health endpoint chỉ là một tiêu chí. Cần thêm giao dịch nghiệp vụ đại diện nếu thay đổi có thể ảnh hưởng đăng nhập, đọc/ghi dữ liệu hoặc tích hợp.

## 10. Điều kiện tiếp tục, quay lui và thu hồi đích cũ

### 10.1. Xác định ngưỡng trước cửa sổ thay đổi

Ví dụ điều kiện tiếp tục:

- Authoritative trả đúng toàn bộ RRset mong muốn.
- Delegation dẫn tới đúng bộ nameserver trong kịch bản chuyển hosting.
- Không xuất hiện lỗi validation DNSSEC ngoài kỳ vọng.
- TLS và endpoint nghiệp vụ đạt kiểm thử từ các vị trí đã chọn.
- Tỷ lệ lỗi và độ trễ nằm trong ngưỡng dịch vụ đã thống nhất.
- Phương án dữ liệu cho phép cả giai đoạn chuyển tiếp và quay lui.

Ghi trước ngưỡng cụ thể phù hợp với hệ thống, người có quyền quyết định và trạng thái cần khôi phục. Không đợi sự cố xảy ra mới tranh luận thế nào là thất bại.

### 10.2. Quay lui cũng là một lần chuyển đổi

Nếu đổi endpoint gây lỗi, khôi phục đầy đủ RRset cũ và kiểm chứng authoritative. Client đã cache IP mới vẫn có thể tiếp tục tới đích mới, nên giữ khả năng xử lý hoặc điều hướng phù hợp ở đó trong giai đoạn chuyển tiếp.

Nếu vừa đổi NS, trả delegation về bộ NS cũ không tức thời kéo mọi resolver về phía cũ. Vì vậy, hai zone phải tiếp tục hoạt động và giữ dữ liệu nhất quán theo kế hoạch.

Không lặp đi lặp lại việc đổi qua lại hai IP chỉ vì các phép thử từ các cache khác nhau chưa khớp. Trạng thái dao động làm khó chẩn đoán và tạo thêm nhiều kết quả đang cache.

Nếu dữ liệu đã thay đổi không tương thích với hệ thống cũ, quay DNS về không đủ để quay lui dịch vụ. Phải có phương án dữ liệu hoặc quyết định phục hồi phù hợp.

### 10.3. Thu hồi dựa trên nhiều tín hiệu

Chỉ thu hồi khi đã đáp ứng:

| Nhóm | Bằng chứng |
| --- | --- |
| DNS | Đã qua cửa sổ TTL/delegation liên quan và kiểm chứng tại các nguồn phù hợp |
| Client | Đã đánh giá cache runtime, client quan trọng và kết nối dài |
| Lưu lượng | Quan sát đủ thời gian theo chu kỳ sử dụng của dịch vụ |
| Dữ liệu | Không còn nhu cầu đồng bộ hoặc quay lui về đích cũ |
| Tổ chức | Chủ dịch vụ chấp nhận kết thúc cửa sổ quay lui |
| Tài nguyên | Có thứ tự gỡ DNS, endpoint, chứng thư và cấu hình phụ thuộc |

“TTL đã hết” là một đầu vào, không phải bằng chứng duy nhất.

## 11. Các tình huống dễ chẩn đoán sai

| Hiện tượng | Điều cần kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| TTL đã hạ nhưng client vẫn dùng IP cũ | Cache được tạo trước thay đổi | Đối chiếu TTL cũ và thời điểm authoritative phục vụ TTL thấp |
| Một số client tốt, số khác lỗi | Resolver, IPv4/IPv6, private view hoặc cache runtime khác nhau | Chia nhóm phép thử theo đường thực tế |
| Authoritative đúng nhưng client NXDOMAIN | Negative cache hoặc hỏi sai namespace | Đọc SOA, resolver và owner name đầy đủ |
| Đổi NS xong một số nơi timeout | Còn cache NS cũ nhưng dịch vụ cũ đã tắt | Khôi phục khả năng trả lời của phía còn được hỏi |
| SERVFAIL sau chuyển nameserver | Chuỗi DS/DNSKEY hoặc delegation không nhất quán | Kiểm tra validation và dữ liệu tại cha/con |
| Website chạy nhưng email lỗi | Thiếu MX/TXT hoặc target mail không đúng | So sánh toàn bộ dữ liệu phụ thuộc email |
| Curl ép IP mới thành công, dùng hostname thất bại | DNS, proxy hoặc cache chưa đúng | So sánh phân giải và đường kết nối thật |
| DNS đúng nhưng phiên đăng nhập lỗi | Cookie, dữ liệu phiên hoặc cấu hình ứng dụng | Điều tra lớp ứng dụng và trạng thái dữ liệu |
| JVM tiếp tục kết nối đích cũ | Cache runtime hoặc connection pool giữ kết nối | Kiểm tra cấu hình JDK và vòng đời kết nối |
| Sau update mất một địa chỉ | Request không chứa đầy đủ RRset cần giữ | Khôi phục tập đúng, sửa quy trình cập nhật |

Không mặc định tăng hoặc giảm TTL sẽ sửa mọi lỗi. TTL không sửa được NS sai, địa chỉ sai, chữ ký không hợp lệ, endpoint hỏng hoặc chứng thư thiếu hostname.

## 12. Tự động hóa, quan sát và chi phí trên OCI

### 12.1. Lưu bằng chứng cho từng bước

Một quy trình có thể review nên giữ được:

- Snapshot cấu hình hiện hành và trạng thái đích mong muốn.
- Danh sách RRset và delegation thực sự bị tác động.
- TTL cũ, thời điểm xác nhận TTL thấp và thời điểm chuyển.
- Kết quả kiểm tra authoritative, resolver và nghiệp vụ.
- Phiên bản hoặc ETag dùng khi cập nhật.
- Người thực hiện, quyết định tiếp tục/quay lui và thời điểm kết thúc.

Dùng Audit để điều tra thao tác quản lý tài nguyên OCI, kết hợp các phép đo DNS và ứng dụng. Log quản lý không phải danh sách đầy đủ mọi client đã nhận kết quả DNS.

### 12.2. Tự động hóa theo giai đoạn

Pipeline nên chia thành chuẩn bị endpoint, hạ TTL, chờ điều kiện, chuyển RDATA hoặc NS, kiểm chứng và kết thúc. Bước chờ phải gắn với dữ liệu TTL đã thu thập và kết quả kiểm tra, không chỉ là một thời gian ngủ cố định áp dụng cho mọi zone.

Kiểm tra kế hoạch hạ tầng dưới dạng mã trước khi áp dụng. Một thay đổi bản ghi không nên vô tình tạo lại zone, xóa NS con hoặc thay cả tập dữ liệu do pipeline khác sở hữu.

Nếu dùng Traffic Management hoặc health check, xác nhận cơ chế trả lời và đối tượng quản lý bản ghi trước khi sửa thủ công. TTL thấp không tự tạo failover; nhiều IP trong A RRset cũng không tự loại backend hỏng.

### 12.3. Cân bằng tốc độ chuyển đổi với chi phí

TTL thấp có thể làm tăng truy vấn authoritative tùy lượng client và hành vi cache. Giữ song song hai load balancer, Compute hoặc hai phía DNS hosting cũng có chi phí trong cửa sổ chuyển tiếp.

Lập ngân sách cho khoảng chạy song song, tần suất probe và thời gian lưu log. Không cắt ngắn giai đoạn giữ hệ thống cũ chỉ để loại một khoản chi chưa được so sánh với yêu cầu khôi phục.

Sau khi ổn định, nâng TTL theo nhu cầu vận hành và thu hồi tài nguyên theo danh sách phụ thuộc. Xóa bản ghi trỏ tới tài nguyên không còn dùng trước khi để target có thể bị người khác tiếp quản, đồng thời tôn trọng cửa sổ cache và kế hoạch chuyển tiếp.

## 13. Bài thực hành có kiểm soát

Dùng một child zone lab được ủy quyền rõ ràng để tránh ảnh hưởng domain chính.

1. Chuẩn bị hai endpoint thử nghiệm trả nội dung nhận diện khác nhau, chẳng hạn `old` và `new`, cùng hỗ trợ hostname lab.
2. Công bố A tới đích cũ và ghi nhận TTL, kết quả authoritative, resolver và ứng dụng.
3. Hạ TTL nhưng giữ địa chỉ cũ; xác nhận đã publish và quan sát TTL ở các lớp khác nhau.
4. Chờ cửa sổ chuẩn bị theo dữ liệu đã ghi.
5. Kiểm thử đích mới bằng `curl --resolve`, xác nhận TLS và nội dung.
6. Đổi A sang đích mới, theo dõi cả hai endpoint và kết quả phân giải.
7. Diễn tập khôi phục RRset cũ; quan sát vì sao các client không đổi cùng một thời điểm.
8. Ghi lại tiêu chí đủ để dừng đích không còn dùng và cách xử lý cache/kết nối dài.

Nếu muốn học chuyển hosting, thực hiện một bài diễn tập tiếp theo trong cùng phạm vi lab: giữ dữ liệu ứng dụng tương đương giữa DNS cũ và OCI, kiểm tra từng nameserver rồi đổi NS tại cha. Với zone có DNSSEC, bổ sung kế hoạch riêng trước khi thao tác.

Một bài thực hành đạt yêu cầu cần giải thích được tại sao dữ liệu cũ còn xuất hiện, chứng minh endpoint mới hoạt động trước khi chuyển, và chỉ rõ cách quay lui trong cả DNS lẫn ứng dụng. Mục tiêu là kiểm soát được giai đoạn chuyển tiếp, thay vì chỉ hoàn thành thao tác đổi một giá trị trên Console.

