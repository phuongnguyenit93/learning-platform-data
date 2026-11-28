# Tier 1 server identity trong mô hình phân tầng truy cập

## Mục tiêu bài học

Trong một mô hình phân tầng truy cập, danh tính quản trị máy chủ cần được giới hạn để sự cố ở một máy hoặc một nhóm máy không dễ lan sang hệ thống định danh, thiết bị người dùng hay toàn bộ hạ tầng.

**Tier 1 server identity** trong bài này là danh tính được dùng hoặc được quản trị trong phạm vi tầng máy chủ ứng dụng và dịch vụ, với quyền, đường đăng nhập và vòng đời phù hợp phạm vi đó. Trọng tâm là danh tính cá nhân dành cho quản trị máy chủ; bài cũng phân biệt chúng với danh tính máy và workload để tránh gộp các loại quyền khác nhau.

Sau bài học, bạn có thể:

- Định nghĩa phạm vi Tier 1 trong một mô hình tiering đã được tổ chức lựa chọn.
- Tách tài khoản quản trị máy chủ khỏi tài khoản hằng ngày và tài khoản quản trị hệ thống định danh.
- Phân biệt danh tính con người, máy chủ, dịch vụ và tài khoản cục bộ.
- Thiết kế giới hạn resource, đường đăng nhập và cấp quyền JIT/JEA.
- Nhận diện các phụ thuộc quản trị có thể làm một hệ thống vượt phạm vi Tier 1.
- Kiểm tra quyền thực tế, credential, phiên và thu hồi theo từng lớp.

Tên tier và cách chia tầng không phải một tiêu chuẩn duy nhất cho mọi tổ chức. Bài sử dụng một mô hình ba tầng minh họa; cần ánh xạ sang kiến trúc và chính sách thực tế trước khi triển khai.

## 1. Tier 1 có nghĩa gì trong bài này?

Một cách phân chia khái niệm:

| Tầng minh họa | Phạm vi chính | Mục tiêu bảo vệ |
|---|---|---|
| Tier 0 | Hệ thống hoặc quyền có thể kiểm soát miền định danh và các cơ chế tin cậy cốt lõi | Tránh việc chiếm một thành phần dẫn tới kiểm soát danh tính hoặc phạm vi hạ tầng rất rộng |
| Tier 1 | Máy chủ ứng dụng, cơ sở dữ liệu và dịch vụ thuộc phạm vi được phân loại | Giới hạn quản trị theo dịch vụ, môi trường và tập tài sản |
| Tier 2 | Thiết bị và hoạt động người dùng hằng ngày theo mô hình này | Giảm đường ảnh hưởng từ môi trường tiếp xúc nhiều nội dung tới hạ tầng quản trị |

Đây là mô hình tham chiếu, không phải quy tắc “mọi server đều là Tier 1”.

Một máy chạy công cụ có thể thay khóa tin cậy, sửa chính sách định danh hoặc điều khiển máy ảo của hệ thống Tier 0 có thể thuộc phạm vi kiểm soát cao hơn, dù hệ điều hành của nó cũng là hệ điều hành máy chủ.

Ngược lại, một cơ sở dữ liệu có dữ liệu kinh doanh rất nhạy cảm không tự trở thành Tier 0 theo định nghĩa quyền kiểm soát định danh. Nó vẫn cần kiểm soát theo độ nhạy và tác động, có thể chia thành những vùng quản trị riêng.

Cần đánh giá cả **khả năng kiểm soát hạ tầng** và **mức độ nhạy cảm nghiệp vụ**. Một nhãn tier không thay thế toàn bộ mô hình rủi ro.

## 2. Danh tính Tier 1 cần bảo vệ ranh giới nào?

Một mục tiêu của tiering là hạn chế việc đưa credential hoặc quyền của một phạm vi tin cậy vào môi trường có thể bị một phạm vi khác kiểm soát.

Ví dụ:

- Không dùng danh tính quản trị hệ thống định danh để đăng nhập bảo trì máy ứng dụng thông thường.
- Không dùng danh tính quản trị máy chủ để đọc email hoặc xử lý tài liệu hằng ngày.
- Không để tài khoản quản trị máy chủ có khả năng quản trị thiết bị người dùng ngoài nhiệm vụ.
- Không để quyền trên một dịch vụ tự lan sang mọi máy chủ cùng tầng.

Các tầng không đơn giản là các mức “cấp cao được vào mọi chỗ”. Đăng nhập bằng một danh tính có quyền rộng lên máy kém tin cậy có thể làm lộ hoặc tạo khả năng lạm dụng quyền đó.

### Ví dụ ranh giới mong muốn

```text
Danh tính hằng ngày
    -> email, trao đổi và ứng dụng công việc thông thường

Danh tính quản trị máy chủ Tier 1
    -> đường quản trị được phép
    -> PAM và quyền JIT
    -> đúng tập máy chủ/dịch vụ Tier 1

Danh tính quản trị miền tin cậy cốt lõi
    -> đường quản trị riêng theo mức bảo vệ tương ứng
    -> không dùng như tài khoản bảo trì máy ứng dụng
```

Một máy trạm quản trị có thể được thiết kế với mức tin cậy phù hợp để khởi tạo công việc Tier 1. Không nên suy ra tier của nguồn chỉ từ việc nó là máy tính để bàn hay laptop. Chức năng, quyền kiểm soát và đường quản lý của nó mới quan trọng.

## 3. Bốn loại danh tính cần phân biệt

### 3.1. Danh tính cá nhân quản trị máy chủ

Đây là tài khoản hoặc principal đại diện cho một người thực hiện nhiệm vụ Tier 1. Nó cần có:

- Chủ sở hữu cá nhân xác định.
- Nguồn cấp và vòng đời gắn với nhân sự.
- Phạm vi tài sản và hành động.
- Điều kiện xác thực, thiết bị và đường truy cập.
- Cơ chế cấp quyền tạm, phê duyệt và bằng chứng phù hợp.

Một người có thể có các danh tính riêng cho những nhiệm vụ khác nhau. Việc dùng tên khác không tự tạo ranh giới nếu credential, nhóm quyền hoặc đường khôi phục vẫn bị gộp.

### 3.2. Danh tính máy chủ

Máy chủ có thể có tài khoản máy, chứng thư hoặc danh tính thiết bị để tham gia miền, xác thực với dịch vụ và nhận cấu hình.

Danh tính đó không phải danh tính của người quản trị đang mở phiên. Cần phân biệt:

- Máy nào đang kết nối.
- Người nào yêu cầu và điều khiển.
- Tài khoản nào thực thi thao tác tại đích.

Tài khoản máy có quyền gì và có thể ảnh hưởng tới đâu cần được đánh giá riêng. Không mặc định mọi danh tính máy trong Tier 1 đều có cùng mức quyền.

### 3.3. Danh tính dịch vụ hoặc workload

Một ứng dụng có thể dùng tài khoản dịch vụ, khóa, chứng thư hoặc danh tính workload để truy cập cơ sở dữ liệu và hệ thống khác.

Danh tính workload cần phạm vi theo chức năng máy, không nên dùng tài khoản cá nhân quản trị làm danh tính chạy lâu dài.

Cũng không nên cho workload quyền quản trị toàn miền chỉ vì nó cần đọc một nguồn dữ liệu. Nếu quyền workload có thể kiểm soát hệ thống tin cậy cốt lõi, phải đánh giá lại ranh giới phân tầng.

### 3.4. Tài khoản cục bộ và tài khoản khẩn cấp

Hệ thống có thể cần tài khoản cục bộ cho quản trị hoặc khôi phục. Những tài khoản này cần được kiểm kê, quản lý credential và giới hạn sử dụng.

Dùng cùng một mật khẩu quản trị cục bộ trên nhiều máy làm tăng phạm vi ảnh hưởng khi bí mật bị lộ. Nếu phù hợp nền tảng, cần cơ chế quản lý riêng từng credential và luân chuyển có kiểm chứng.

Tài khoản khẩn cấp không phải ngoại lệ vô thời hạn cho mọi ranh giới. Nó cần điều kiện sử dụng, người có trách nhiệm, phạm vi và bằng chứng.

## 4. Tách danh tính cá nhân theo nhiệm vụ

Một sơ đồ đặt tên minh họa:

| Danh tính | Mục đích |
|---|---|
| `trang.user` | Công việc hằng ngày |
| `trang.server` | Quản trị máy chủ thuộc phạm vi Tier 1 |
| `trang.identity` | Nhiệm vụ quản trị miền tin cậy cốt lõi, nếu người đó được giao |

Tên chỉ là dấu hiệu hỗ trợ. Quyền hiệu lực, điều kiện đăng nhập và vòng đời mới quyết định ranh giới.

### 4.1. Không dùng credential chung

Nếu các tài khoản dùng cùng bí mật hoặc có một đường khôi phục yếu cho phép chiếm tất cả, việc tách tên mang lại ít giá trị hơn mong muốn.

Cần kiểm soát quá trình cấp, đăng ký phương thức xác thực, phục hồi, khóa và rà soát. Mỗi danh tính phải có mục đích và người chịu trách nhiệm rõ.

### 4.2. Tách danh tính không đồng nghĩa quyền thường trực

Một tài khoản `trang.server` có thể tồn tại để quy trách nhiệm, nhưng quyền quản trị máy chủ có thể chỉ được kích hoạt cho một công việc.

Ví dụ, tài khoản được phép yêu cầu profile bảo trì; grant JIT mới tạo quyền trên máy cụ thể trong cửa sổ đã duyệt.

Không nên chuyển mọi người có hậu tố `.server` thành quản trị viên thường trực của toàn bộ tầng.

### 4.3. Truy vết khi phải dùng tài khoản kỹ thuật chung

Một hệ thống cũ có thể buộc PAM sử dụng tài khoản kỹ thuật tại đích. Khi đó cần ánh xạ phiên từ danh tính cá nhân tới tài khoản thực thi và giữ credential trong cơ chế quản lý phù hợp.

Nếu nhiều phiên cùng tài khoản khiến log đích không phân biệt được người điều khiển, cần xử lý giới hạn đó bằng thiết kế phiên hoặc quy trình. Không kết luận có quy trách nhiệm cá nhân chỉ từ một tên tài khoản chung.

## 5. Phân loại bằng đường kiểm soát thực tế

Không chỉ hỏi máy chủ đang phục vụ ứng dụng gì. Cần hỏi ai có thể điều khiển máy đó và máy đó có thể điều khiển hệ thống nào khác.

### 5.1. Những phụ thuộc có thể làm vượt tầng

| Thành phần hoặc quyền | Câu hỏi phân loại |
|---|---|
| Nền tảng ảo hóa | Có thể thay đĩa, bộ nhớ hoặc cấu hình máy thuộc phạm vi tin cậy cao hơn không? |
| Hệ thống sao lưu và phục hồi | Có thể đọc dữ liệu nhạy cảm hoặc phục hồi nội dung điều khiển lên hệ thống cao hơn không? |
| Công cụ triển khai cấu hình | Có thể đẩy mã hoặc chính sách lên các hệ thống ngoài Tier 1 không? |
| Kho mã, hiện vật và pipeline | Có thể thay mã được thực thi đặc quyền trong phạm vi khác không? |
| Hạ tầng chứng thư hoặc khóa | Có thể phát hành hoặc thay bí mật tạo ra quan hệ tin cậy cao hơn không? |
| Công cụ quản lý endpoint/PAW | Có thể điều khiển nguồn khởi tạo phiên quản trị không? |
| PAM và vault | Có thể cấp quyền, tiết lộ bí mật hoặc mở phiên tới những phạm vi nào? |

Nếu một danh tính quản trị máy ứng dụng cũng quản trị được một nền tảng có quyền kiểm soát Tier 0, ranh giới dự kiến đã bị vượt qua.

Cách xử lý có thể gồm thu hẹp quyền, tách nền tảng quản lý hoặc nâng mức bảo vệ và phân loại thành phần. Không chỉ đổi nhãn của tài khoản rồi giữ nguyên mọi đường kiểm soát.

### 5.2. Phân đoạn trong cùng Tier 1

Tier 1 có thể rất rộng: thanh toán, nhân sự, báo cáo và nhiều môi trường khác nhau. Hai tài sản cùng tier không có nghĩa mọi quản trị viên của tài sản này được quản trị tài sản kia.

Nên phân scope theo dịch vụ, đơn vị, môi trường hoặc trách nhiệm vận hành. Những phạm vi nhạy cảm có thể cần nhóm và đường truy cập riêng.

Một máy thử nghiệm cũng không nên là nơi đưa credential quản trị sản xuất vào chỉ vì cả hai cùng được gọi là Tier 1.

### 5.3. Phụ thuộc xác thực không đồng nghĩa quyền quản trị

Máy chủ ứng dụng có thể cần phân giải tên, đồng bộ thời gian hoặc xác thực với dịch vụ định danh. Không thể suy ra mọi kết nối đến hạ tầng định danh đều vi phạm tiering.

Cần phân biệt:

- Sử dụng một dịch vụ theo quyền thông thường cần thiết.
- Có khả năng quản trị, thay đổi hoặc chiếm quyền kiểm soát dịch vụ đó.
- Đưa credential đặc quyền của phạm vi tin cậy cao vào máy chủ ứng dụng.

Chính sách mạng và danh tính phải đủ chi tiết để cho phép phụ thuộc hợp lệ mà không mở đường quản trị ngoài ý định.

## 6. Giới hạn đăng nhập và đường sử dụng danh tính Tier 1

### 6.1. Nguồn quản trị

Danh tính Tier 1 nên được sử dụng từ nguồn quản trị đáp ứng điều kiện, chẳng hạn PAW hoặc một kiến trúc được đánh giá tương đương cho nhiệm vụ đó.

Không dùng danh tính này cho email, web thông thường hoặc từ một máy nguồn không đạt điều kiện chỉ vì kết nối đích đi qua một jump host.

Một máy trung gian được quản lý không tự loại bỏ rủi ro từ endpoint điều khiển đầu vào đã bị xâm nhập.

### 6.2. Đích và kiểu đăng nhập

Cần xác định tài sản và loại sử dụng được phép:

- Đăng nhập quản trị tương tác.
- Phiên điều khiển từ xa.
- Truy cập API hoặc mạng để quản trị.
- Chạy tác vụ theo lịch.
- Chạy dịch vụ.

Chúng có cơ chế quyền và hành vi khác nhau. Một giới hạn chỉ áp dụng đăng nhập tại console có thể không chặn đường truy cập từ xa hoặc API.

Ngược lại, chặn một kiểu xác thực mạng thiếu phân tích có thể làm hỏng phụ thuộc ứng dụng. Cần ánh xạ chính sách sang cơ chế nền tảng và thử nghiệm theo từng loại.

Danh tính cá nhân quản trị không nên được dùng làm tài khoản chạy dịch vụ hoặc tác vụ lâu dài. Danh tính workload cũng không nên có quyền đăng nhập tương tác rộng nếu công việc không cần.

### 6.3. Nhiều lớp cùng thực thi

Một kiểm soát có thể gồm:

- Chính sách danh tính xác định người và nguồn được phép.
- Điều kiện thiết bị tại điểm truy cập.
- PAM giới hạn resource, tài khoản và profile.
- Phân đoạn mạng giới hạn đường quản trị.
- Quyền đăng nhập và quyền thực thi tại máy đích.
- Giám sát và phát hiện đường ngoài thiết kế.

Một OU, tên nhóm hoặc nhãn tier có thể hỗ trợ quản trị nhưng không tự tạo ra ranh giới. Cần quyền và chính sách thực thi tương ứng.

Nếu vẫn còn đường dùng cùng credential để đăng nhập trực tiếp ngoài PAM, phải đánh giá và kiểm soát đường đó.

### 6.4. Tránh mang credential giữa phạm vi

Không đăng nhập bằng danh tính quản trị miền tin cậy cốt lõi lên máy Tier 1 để “làm nhanh”, cũng không dùng danh tính Tier 1 trên thiết bị hằng ngày.

Mức lộ credential, ticket, token hoặc khả năng sử dụng phiên phụ thuộc giao thức và cấu hình. Không mặc định rằng đi qua PAM hoặc dùng đăng nhập từ xa luôn loại bỏ mọi dạng credential khỏi các thành phần trung gian.

Cần biết cơ chế nào được dùng, bí mật xuất hiện ở đâu và hệ thống nào có thể điều khiển phiên.

## 7. Cấp quyền Tier 1 qua PAM

### 7.1. Mô tả công việc thay vì cấp cả tầng

Một yêu cầu phù hợp có thể là:

> Trang cần đọc log và khởi động lại dịch vụ thanh toán trên asset-2041 trong cửa sổ bảo trì. Không cần quản trị thư mục, tài sản người dùng hay các máy chủ báo cáo.

PAM cần đánh giá đúng principal, resource, hành động, thời gian và điều kiện, rồi ánh xạ sang quyền đích đủ hẹp.

### 7.2. Mẫu ý định chính sách

```yaml
tier1_access_intent:
  principal_reference: person-trang-server
  purpose: payments-service-maintenance
  source:
    workstation_profile: managed-tier1-admin-source
    authentication_profile: privileged-human-strong
  target_scope:
    tier: tier1
    resource_ids:
      - asset-2041
  allowed_profile: service-restart-limited
  activation:
    require_approval: true
    maximum_duration_minutes: 30
    require_current_identity_status: true
  credential_handling:
    disclose_to_operator: false
  excluded_administrative_scopes:
    - core-identity-control
    - user-endpoint-administration
    - unrelated-server-services
  session:
    controlled_path_required: true
    required_evidence: session-and-target-events
```

Đây là mô hình ý định, không phải schema cấu hình. Các nhãn nguồn và profile phải được chuyển thành điều kiện, quyền và khả năng thực thi có thật.

30 phút là giá trị minh họa. Không có thời lượng chung phù hợp mọi nhiệm vụ.

### 7.3. JIT và JEA bổ sung cho tiering

Tiering xác định ranh giới quản trị. JIT giới hạn thời gian quyền tồn tại. JEA giới hạn hành động được thực hiện.

Một tài khoản Tier 1 có quản trị toàn bộ máy chủ vô thời hạn vẫn có phạm vi ảnh hưởng lớn. Một grant ngắn nhưng cho phép tạo quyền tồn tại lâu dài cũng cần được đánh giá.

Với profile hạn chế, cần kiểm tra công cụ và thao tác thực tế. Danh sách tên lệnh không đủ nếu công cụ đó có thể mở shell, sửa thành phần thực thi hoặc tạo một đường quyền khác.

### 7.4. PAM và hạ tầng quản lý phải phù hợp tầng được kiểm soát

Một broker, vault hoặc hệ thống quản lý có thể ảnh hưởng nhiều phạm vi. Cần bảo vệ nó theo khả năng điều khiển thực tế và thiết kế cách tách quyền, dữ liệu, phiên cùng đường quản trị.

Một nhãn “broker Tier 1” không đủ nếu quản trị viên của nó có thể lấy credential Tier 0. Nếu dùng nền tảng chung, ranh giới và quyền quản trị giữa các phạm vi phải được đánh giá, không chỉ tách bằng tên thư mục.

## 8. Danh tính máy và workload trong phạm vi Tier 1

### 8.1. Quyền của danh tính máy

Kiểm tra máy chủ được phép truy cập dịch vụ nào, có thể đọc bí mật gì và có quyền sửa đối tượng hoặc cấu hình ở đâu.

Việc máy là thành viên của một miền không có nghĩa người quản trị máy được quyền quản trị miền. Tuy nhiên, quyền trên máy có thể cho phép tiếp cận dữ liệu và credential của workload chạy trên đó, nên cần tính vào phạm vi ảnh hưởng.

### 8.2. Danh tính workload

Tài khoản dịch vụ nên gắn với mục đích và tài sản cần dùng, có chủ sở hữu và vòng đời. Khi có cơ chế phù hợp, ưu tiên cách cấp credential và quyền giảm bí mật dài hạn hoặc dùng chung không cần thiết.

Cần đánh giá tác động khi luân chuyển: ứng dụng nào phụ thuộc, cách nhận credential mới và cách kiểm tra vận hành. Không đổi bí mật thiếu kiểm soát làm gián đoạn dịch vụ.

### 8.3. Không lấy MFA của người dùng làm cơ chế tự động hóa

Tác vụ máy không nên giữ phiên của `trang.server`, chia sẻ OTP hoặc dùng mã khôi phục để chạy định kỳ.

Nếu người quản trị tạo hoặc thay đổi một tác vụ đặc quyền, hành động đó cần được kiểm soát. Danh tính thực thi của tác vụ vẫn phải được cấp quyền riêng theo chức năng và phạm vi.

## 9. Vòng đời và thu hồi danh tính Tier 1

### 9.1. Cấp và rà soát

Danh tính quản trị máy chủ cần được cấp theo nhiệm vụ, không chỉ theo chức danh. Hồ sơ nên thể hiện người sở hữu, phạm vi dịch vụ, nguồn phê duyệt và điều kiện sử dụng.

Khi nhân sự chuyển nhóm, cần đánh giá cả entitlement, membership, grant đang hoạt động và quyền trực tiếp tại đích. Không mặc định danh tính quản trị cũ được giữ nguyên chỉ vì tài khoản hằng ngày vẫn hoạt động.

Rà soát cần nhìn quyền có hiệu lực, gồm quyền kế thừa, nhóm chồng lấn và quyền qua công cụ quản lý. Một danh sách tên tài khoản không đủ để hiểu phạm vi.

### 9.2. Credential và bí mật

Credential cần có chủ sở hữu, resource liên quan, cách sử dụng và kế hoạch xử lý sau checkout hoặc sự cố.

Với tài khoản cục bộ hoặc tài khoản kỹ thuật chung, cần biết credential có được dùng trên nhiều máy không. Sự lặp lại bí mật có thể làm một sự cố cục bộ trở thành đường lan rộng trong Tier 1 hoặc vượt tier.

Không lưu credential quản trị cao hơn trong script, tệp cấu hình hoặc công cụ hỗ trợ trên máy Tier 1. Nếu một workload thật sự cần một quyền nhạy cảm, phải thiết kế và đánh giá quan hệ đó, không giấu dưới nhãn “tài khoản dịch vụ”.

### 9.3. Thu hồi theo nhiều lớp

| Lớp | Điều cần kiểm chứng |
|---|---|
| Danh tính | Tài khoản bị khóa hoặc giới hạn đúng chính sách |
| Eligibility và nhóm | Không còn yêu cầu hoặc kích hoạt quyền ngoài nhiệm vụ |
| Grant | Các lần cấp đang tồn tại được xử lý theo điều kiện thu hồi |
| Phiên PAM | Không mở mới hoặc nối lại khi không được phép |
| Đích | Quyền tạm và phiên đích không còn tồn dư ngoài chính sách |
| Credential và token | Bí mật hoặc bằng chứng truy cập liên quan được xử lý phù hợp |
| Tác vụ và đường truy cập mới | Không bỏ sót cơ chế đã được tạo trong lúc quyền có hiệu lực |

Đổi mật khẩu không tự bảo đảm mọi phiên đang mở kết thúc. Ngắt kết nối không tự hoàn tác thay đổi hoặc dừng mọi tác vụ nền.

Khi thu hồi một grant, phải phân biệt phần quyền do grant tạo ra với phần quyền còn hợp lệ từ nguồn khác. Cần tránh tác vụ thu hồi đến muộn xóa nhầm quyền của lần cấp mới.

### 9.4. Khi danh tính bị nghi lộ

Cần đánh giá những tài sản mà danh tính có thể điều khiển, những phiên và credential liên quan, cùng đường đi tới công cụ quản lý hoặc phạm vi khác.

Sự cố trên một máy Tier 1 không mặc định đồng nghĩa Tier 0 đã bị chiếm. Tuy nhiên, nếu từng dùng credential cao hơn trên máy đó hoặc tồn tại đường điều khiển ngược, phạm vi điều tra phải bao gồm quan hệ đó.

Xử lý nên theo bằng chứng và khả năng thực tế, đồng thời thu hồi quyền đang gây rủi ro theo quy trình có trách nhiệm.

## 10. Tình huống thực hành: bảo trì máy chủ thanh toán

### 10.1. Bối cảnh

Trang có danh tính hằng ngày và danh tính quản trị máy chủ riêng. Trang cần bảo trì dịch vụ trên `asset-2041`.

Thiết kế mong muốn:

- Danh tính hằng ngày không mở phiên quản trị sản xuất.
- Danh tính Tier 1 chỉ dùng từ nguồn quản trị phù hợp.
- Trang được yêu cầu profile bảo trì cho đúng tài sản.
- Quyền được cấp có thời hạn, không tiết lộ credential khi không cần.
- Không có quyền quản trị hạ tầng định danh, thiết bị người dùng hoặc máy chủ dịch vụ khác.
- Phiên và thu hồi có bằng chứng.

### 10.2. Các yêu cầu và quyết định

| Yêu cầu | Hành vi mong muốn |
|---|---|
| Trang đọc email bằng tài khoản hằng ngày | Thực hiện ở môi trường công việc thông thường |
| Trang dùng danh tính Tier 1 từ máy hằng ngày không đạt điều kiện | Không mở đường quản trị theo chính sách |
| Trang dùng nguồn phù hợp nhưng chưa có phê duyệt | Chưa kích hoạt quyền bắt buộc có phê duyệt |
| Trang mở phiên đúng resource, profile và cửa sổ | Cho phép với các giới hạn đã xác định |
| Trang đổi đích sang máy báo cáo ngoài phạm vi | Từ chối |
| Trang yêu cầu credential quản trị miền tin cậy cốt lõi | Không thuộc entitlement của danh tính Tier 1 |
| Trang dùng danh tính Tier 1 để quản trị máy người dùng | Không thuộc đường sử dụng được thiết kế |
| Công việc hoàn tất trước hạn | Thu hồi sớm theo quy trình và kiểm chứng |

### 10.3. Biến thể: cần sửa lỗi liên quan tới định danh

Trong lúc bảo trì, Trang phát hiện một lỗi cấu hình liên quan tới dịch vụ định danh.

Không nên giải quyết bằng cách đăng nhập tài khoản quản trị cao hơn ngay trên máy ứng dụng. Cần chuyển phần công việc sang người và đường quản trị phù hợp, xác định resource cùng phạm vi cần thay đổi.

Nếu Trang đồng thời được giao vai trò cao hơn, vẫn phải sử dụng đúng danh tính và nguồn quản trị của vai trò đó. Một người giữ nhiều nhiệm vụ không có nghĩa mọi credential được dùng lẫn trong một phiên.

### 10.4. Biến thể: công cụ backup bị xếp nhầm

Một máy backup được ghi là Tier 1 vì “là server hỗ trợ”. Điều tra phát hiện quản trị viên của máy có thể sửa bản phục hồi dùng cho hệ thống định danh cốt lõi.

Cần đánh giá khả năng kiểm soát này. Biện pháp có thể gồm tách phạm vi backup, thu hẹp quyền quản trị hoặc bảo vệ thành phần theo mức tương ứng.

Nếu chỉ giữ nhãn Tier 1 rồi tiếp tục cho đội máy chủ ứng dụng quản trị toàn bộ, ranh giới trên giấy không khớp khả năng thực tế.

### 10.5. Biến thể: phiên kết thúc nhưng quyền còn

Grant hết hạn và broker đóng phiên, nhưng membership tạm ở đích chưa được gỡ.

Cần phản ánh thu hồi chưa hoàn tất, giao người xử lý và đối soát. Không coi trạng thái phiên đã đóng là bằng chứng duy nhất rằng danh tính không còn quyền.

Nếu có tác vụ được khởi chạy trong phiên, cần đánh giá nó riêng. Sự tồn tại của tác vụ không tự được quyết định bởi trạng thái cửa sổ PAM.

## 11. Kiểm chứng ranh giới Tier 1

Thực hiện trong môi trường, tài khoản và tài sản được phép. Mục tiêu là xác nhận quyền và đường đăng nhập thực tế.

| Phép thử | Kết quả mong đợi |
|---|---|
| Dùng danh tính hằng ngày mở quản trị Tier 1 | Không nhận quyền ngoài thiết kế |
| Dùng danh tính Tier 1 từ nguồn không đáp ứng | Bị chặn tại điểm kiểm soát phù hợp |
| Dùng danh tính Tier 1 quản trị đích Tier 0 | Không thành công theo ranh giới đã xác định |
| Dùng danh tính Tier 1 quản trị endpoint người dùng | Không có quyền ngoài nhiệm vụ |
| Dùng danh tính đặc quyền cao hơn lên máy ứng dụng | Chính sách đăng nhập và đường vận hành ngăn việc dùng sai phạm vi |
| Truy cập máy Tier 1 khác dịch vụ | Không được cho phép chỉ vì cùng tier |
| Kiểm tra đăng nhập tương tác, từ xa, API và tác vụ | Giới hạn bao phủ đúng các kiểu sử dụng |
| Gọi trực tiếp đường quản trị bỏ PAM | Không tạo đường vượt ngoài thiết kế |
| Kích hoạt khi thiếu phê duyệt hoặc grant hết hạn | Không cấp quyền đặc biệt |
| Thử thao tác vượt profile hạn chế | Điểm thực thi chặn theo khả năng đã thiết kế |
| Workload thử quyền ngoài chức năng | Không có quyền rộng mặc định |
| Thu hồi người dùng trong lúc có phiên | Các lớp phiên, grant và đích được xử lý có bằng chứng |
| Kiểm tra quyền trên backup, ảo hóa, triển khai | Phát hiện đường điều khiển vượt ranh giới |
| Thay membership hoặc phạm vi tài sản | Hiệu lực và vòng đời cập nhật đúng chính sách |
| Dùng đường khẩn cấp | Có điều kiện, trách nhiệm, thời hạn và rà soát |
| Kiểm tra trạng thái đích sau thu hồi | Không bỏ qua quyền hoặc phiên tồn dư |

Không cần chặn mọi giao tiếp giữa các tầng. Các phép thử phải phân biệt phụ thuộc dịch vụ hợp lệ với khả năng quản trị hoặc đưa credential sai phạm vi.

Nếu một giới hạn chỉ được phát hiện mà chưa được chặn, hồ sơ cần ghi đúng. Không mô tả cảnh báo như một ranh giới kỹ thuật đã được thực thi.

## 12. Bằng chứng phục vụ vận hành và audit

Một chuỗi bằng chứng nên nối được:

```text
Người sở hữu danh tính
    -> Vai trò và phạm vi Tier 1
    -> Nguồn quản trị và bằng chứng xác thực
    -> Yêu cầu/phê duyệt
    -> Grant cho resource và profile
    -> Phiên cá nhân và tài khoản thực thi
    -> Hoạt động tại đích
    -> Thu hồi và kết quả kiểm chứng
```

Dữ liệu hữu ích gồm:

- Danh tính hằng ngày, quản trị và mối liên hệ chủ sở hữu được bảo vệ.
- Membership, entitlement và phiên bản phạm vi tài sản.
- Phân loại tier và căn cứ về khả năng điều khiển.
- Nguồn truy cập, loại đăng nhập và tài sản đích.
- Phê duyệt, grant, profile và thời điểm.
- Credential tham chiếu, không phải giá trị bí mật.
- Sự kiện bị chặn, đường khẩn cấp và thay đổi cấu hình.
- Kết quả gỡ quyền, ngắt phiên hoặc luân chuyển liên quan.

Cần lưu được lịch sử đủ để giải thích quyết định quá khứ. Membership hoặc nhãn tier hiện tại không tự chứng minh phạm vi của một grant cũ.

Bằng chứng cũng có thể chứa thông tin hạ tầng và dữ liệu nhạy cảm. Cần phân quyền đọc, bảo vệ toàn vẹn, thời gian lưu và dấu vết truy cập phù hợp.

## 13. Những sai lầm thường gặp

**Coi mọi máy chủ đều là Tier 1.** Khả năng điều khiển định danh hoặc hạ tầng cao hơn có thể làm thay đổi phân loại.

**Cho rằng tier cao hơn được đăng nhập mọi nơi.** Việc đưa credential mạnh vào máy kém tin cậy có thể làm mất ranh giới.

**Tách tên tài khoản nhưng dùng chung bí mật hoặc nhóm quyền.** Ranh giới cần nằm trong quyền và đường sử dụng thực tế.

**Gộp toàn bộ Tier 1 thành một tập admin.** Cần phạm vi theo dịch vụ và nhiệm vụ.

**Dùng tài khoản cá nhân quản trị để chạy dịch vụ.** Workload cần danh tính và vòng đời riêng.

**Xem OU hoặc nhãn tier là cơ chế chặn.** Cần chính sách và điểm thực thi tương ứng.

**Bỏ qua backup, ảo hóa và công cụ triển khai.** Các thành phần này có thể tạo đường điều khiển vượt tầng.

**Coi PAM không hiển thị mật khẩu là đủ.** Người điều khiển phiên vẫn có khả năng hành động trong phạm vi quyền của phiên.

**Đóng phiên rồi mặc định thu hồi xong.** Quyền, token và tác vụ tại đích có thể cần xử lý thêm.

## 14. Tự kiểm tra

1. Vì sao một máy backup không tự thuộc Tier 1 chỉ vì nó là server?
2. Danh tính quản trị cá nhân khác danh tính máy và workload thế nào?
3. Tại sao không dùng tài khoản quản trị hệ thống định danh để sửa máy ứng dụng?
4. Người đủ điều kiện dùng tài khoản Tier 1 có nên là admin thường trực mọi server không?
5. Cùng một tier có nghĩa được quản trị chéo mọi dịch vụ không?
6. Vì sao cần kiểm tra nhiều kiểu đăng nhập?
7. Một máy ứng dụng liên hệ dịch vụ định danh có tự vi phạm tiering không?
8. Grant hết hạn và phiên PAM đóng đã đủ xác nhận không còn quyền chưa?

### Gợi ý trả lời

1. Cần xem nó có thể đọc, sửa hoặc phục hồi những hệ thống nào; khả năng kiểm soát có thể vượt phạm vi máy chủ ứng dụng.
2. Danh tính cá nhân quy trách nhiệm con người; danh tính máy xác thực thiết bị; workload thực hiện chức năng tự động theo quyền riêng.
3. Máy ứng dụng có thể trở thành nơi làm lộ hoặc lạm dụng credential và phiên có phạm vi rộng hơn.
4. Không. Nên giới hạn theo resource, nhiệm vụ và cấp quyền có thời hạn khi phù hợp.
5. Không. Tiering không thay phân đoạn dịch vụ và least privilege.
6. Một giới hạn có thể chỉ chặn console nhưng bỏ đường từ xa, API hoặc tác vụ.
7. Không. Cần phân biệt sử dụng phụ thuộc hợp lệ với quyền quản trị hoặc việc đưa credential sai phạm vi.
8. Chưa đủ. Cần kiểm chứng quyền, phiên đích, credential/token và trạng thái còn tồn tại theo chính sách.

## Kết luận

Tier 1 server identity cần được quản trị theo khả năng điều khiển thực tế: đúng người, đúng nguồn quản trị, đúng tập máy chủ và đúng loại hành động. Việc tách danh tính chỉ có giá trị khi quyền, credential và đường đăng nhập cùng giữ ranh giới đó.

Kết hợp tiering với least privilege, JIT/JEA, vault, kiểm soát phiên và thu hồi có bằng chứng giúp hạn chế phạm vi ảnh hưởng khi một máy hoặc danh tính gặp sự cố. Những phụ thuộc như backup, ảo hóa và PAM cũng phải được đánh giá để ranh giới phân tầng phản ánh hệ thống thực tế.
