# Thiết kế golden image với các thành phần dùng chung

Trong một hệ thống chạy trên máy ảo đám mây, nhiều máy thường cần cùng một nền tảng: hệ điều hành đã cập nhật, cấu hình bảo mật cơ bản, chứng thư CA nội bộ, công cụ giám sát và các gói runtime chuẩn. Nếu mỗi nhóm tự cài đặt các thành phần này theo cách riêng, máy chủ dễ khác nhau về phiên bản, cấu hình và mức độ an toàn. Khi xảy ra sự cố, việc tìm nguyên nhân và tái tạo môi trường cũng khó hơn.

**Golden image** là ảnh máy ảo nền đã được tổ chức kiểm duyệt, kiểm thử và phát hành để tạo ra các máy mới theo một chuẩn thống nhất. Ảnh này chứa hệ điều hành cùng những thành phần dùng chung cần thiết cho nhiều workload. Khi tạo máy ảo từ golden image, nhóm vận hành có một điểm xuất phát lặp lại được thay vì cài đặt thủ công từ đầu.

Golden image là một phần của quy trình quản lý hạ tầng. Chất lượng của nó phụ thuộc vào cách xác định thành phần chung, cách xây dựng ảnh, kiểm thử, phát hành phiên bản và cập nhật định kỳ. Một ảnh máy tốt cần đủ chuẩn hóa để các máy nhất quán, đồng thời giữ phần cấu hình riêng của từng môi trường ở giai đoạn triển khai.

## 1. Xác định mục tiêu và phạm vi của golden image

Trước khi tạo ảnh, hãy xác định ảnh sẽ phục vụ loại workload nào và những tiêu chuẩn nào phải được đáp ứng. Một ảnh dùng cho máy chủ ứng dụng Linux có thể khác ảnh dành cho máy Windows chạy dịch vụ doanh nghiệp hoặc máy xử lý dữ liệu. Không nên cố gộp mọi loại máy vào một ảnh nếu chúng có yêu cầu hệ điều hành, bảo mật và vòng đời khác nhau.

Golden image thường giải quyết các mục tiêu sau:

- **Nhất quán:** máy mới được tạo từ cùng một phiên bản ảnh có hệ điều hành, package và cấu hình nền giống nhau.
- **Khởi tạo nhanh:** những thành phần cài đặt giống nhau cho mọi máy đã được chuẩn bị sẵn trong ảnh.
- **Bảo mật có thể kiểm tra:** baseline hardening, bản vá và công cụ bảo vệ được áp dụng trước khi ảnh phát hành.
- **Khả năng tái tạo:** có thể tạo lại máy từ ảnh và cấu hình đã quản lý trong mã nguồn.
- **Kiểm soát thay đổi:** mỗi lần cập nhật tạo ra phiên bản ảnh mới, có lịch sử, kết quả kiểm thử và khả năng quay lại phiên bản trước.

Phạm vi ảnh nên tập trung vào những thành phần ổn định và được dùng chung. Ví dụ:

| Nhóm thành phần | Nội dung có thể đưa vào ảnh | Lý do |
|---|---|---|
| Hệ điều hành | Bản phân phối, phiên bản, kernel và gói hệ thống đã được phê duyệt | Tạo nền tảng thống nhất |
| Bản vá và hardening | Security update, cấu hình SSH/RDP, quyền mặc định, chính sách audit | Giảm cấu hình yếu và lỗ hổng đã biết |
| Chứng thư tin cậy | CA bundle công khai và CA doanh nghiệp được phép phân phối | Giúp ứng dụng xác thực dịch vụ đúng cách |
| Công cụ vận hành | Agent giám sát, log, kiểm kê tài sản và quản lý cấu hình | Chuẩn hóa khả năng quan sát và quản trị |
| Runtime dùng chung | Java runtime, .NET runtime hoặc thư viện nền nếu nhiều workload cần cùng phiên bản | Giảm thời gian cài đặt và sai khác phiên bản |
| Công cụ khởi tạo | Cloud-init hoặc cơ chế bootstrap tương đương | Nhận cấu hình riêng khi máy khởi động |

Không phải thành phần nào cũng cần đưa vào ảnh. Nếu một runtime chỉ phục vụ một ứng dụng, có thể đóng gói cùng ứng dụng hoặc cài trong bước triển khai riêng. Nếu ảnh chứa quá nhiều công cụ không cần thiết, bề mặt tấn công và thời gian cập nhật sẽ tăng lên.

## 2. Phân biệt thành phần chung và cấu hình riêng của workload

Ranh giới quan trọng nhất khi thiết kế golden image là xác định thứ gì giống nhau trên mọi máy và thứ gì thay đổi theo ứng dụng, môi trường hoặc từng instance.

**Nên đưa vào golden image** những thành phần có vòng đời tương đối ổn định, được quản trị tập trung và có thể dùng lại an toàn: hệ điều hành, bản vá, package nền, agent giám sát, CA bundle, chính sách bảo mật mặc định và runtime đã được chuẩn hóa.

**Nên cung cấp khi triển khai hoặc lúc khởi động** những thông tin thay đổi theo môi trường: tên dịch vụ, endpoint cơ sở dữ liệu, vùng triển khai, subnet, tag tài nguyên, cấu hình ứng dụng, feature flag và thông tin định danh của instance. Các giá trị này thường được truyền qua user data, cloud-init, hệ thống quản lý cấu hình, service discovery hoặc dịch vụ cấu hình tập trung.

**Không nhúng bí mật vào ảnh.** Không lưu mật khẩu, private key, token truy cập, API key, credential cơ sở dữ liệu hoặc chứng thư riêng của một máy trong golden image. Mọi máy được tạo từ cùng ảnh đều có thể nhận bản sao của dữ liệu đó; nếu ảnh bị chia sẻ hoặc lộ ra ngoài, bí mật sẽ bị lộ theo. Hãy lấy bí mật lúc chạy từ secret manager bằng danh tính workload có quyền tối thiểu, đồng thời ghi nhận và xoay vòng quyền truy cập theo chính sách.

Một số dữ liệu trạng thái riêng của máy cũng cần được tạo mới khi khởi động, chẳng hạn machine ID, SSH host key, danh tính agent và thông tin đăng ký vào hệ thống quản trị. Nếu ảnh chứa sẵn các giá trị này, nhiều máy có thể xuất hiện với cùng một danh tính, gây nhầm lẫn trong giám sát, xác thực hoặc quản lý tài sản.

| Loại dữ liệu | Vị trí phù hợp | Ví dụ |
|---|---|---|
| Thành phần nền dùng chung | Golden image | OS package, agent, CA bundle |
| Cấu hình môi trường | Bootstrap hoặc config management | Region, endpoint, tên môi trường |
| Cấu hình ứng dụng | Hệ thống triển khai ứng dụng | Phiên bản ứng dụng, tham số runtime |
| Bí mật và khóa riêng | Secret manager hoặc cơ chế cấp phát danh tính an toàn | DB password, API token, private key |
| Danh tính duy nhất của máy | Sinh mới khi khởi tạo | SSH host key, machine ID, agent ID |

Ranh giới này giúp ảnh có thể dùng lại ở nhiều môi trường mà không mang theo cấu hình cũ hoặc thông tin nhạy cảm.

## 3. Thiết kế baseline hệ điều hành và bảo mật

Golden image cần bắt đầu từ một hệ điều hành còn được nhà cung cấp hỗ trợ. Hãy chọn phiên bản có vòng đời phù hợp, cập nhật bảo mật đều đặn và tương thích với ứng dụng. Tránh xây dựng ảnh mới dựa trên một bản hệ điều hành đã hết hỗ trợ vì việc vá lỗi và nhận hỗ trợ sẽ bị giới hạn.

Baseline nên được mô tả thành các quy tắc có thể kiểm tra tự động, thay vì một danh sách thao tác thủ công. Tùy hệ điều hành và workload, baseline có thể gồm:

- Cài đặt security update và loại bỏ package không cần thiết.
- Tắt dịch vụ, cổng lắng nghe và giao thức không sử dụng.
- Giới hạn quyền tài khoản, nhóm quản trị và quyền truy cập file.
- Cấu hình SSH hoặc RDP an toàn, giới hạn phương thức xác thực và nguồn truy cập quản trị.
- Bật đồng bộ thời gian, ghi log hệ thống và audit phù hợp.
- Cấu hình firewall máy chủ theo nguyên tắc chỉ mở những luồng cần thiết.
- Cài agent bảo vệ endpoint hoặc công cụ phát hiện xâm nhập nếu tổ chức yêu cầu.
- Thiết lập CA bundle và chính sách TLS phù hợp với hệ thống nội bộ.

Nên tham chiếu một baseline được tổ chức phê duyệt, ví dụ tiêu chuẩn hardening nội bộ hoặc một profile CIS phù hợp với bản phân phối. Không áp dụng máy móc mọi quy tắc bảo mật mà không kiểm tra tính tương thích. Một cấu hình chặn dịch vụ hoặc thay đổi quyền có thể làm agent giám sát hay ứng dụng hợp lệ không hoạt động.

Tách **baseline bắt buộc** khỏi **tùy chọn theo workload**. Ví dụ, audit hệ thống và giới hạn quyền quản trị có thể là yêu cầu chung; cấu hình module kernel đặc thù hoặc runtime chuyên dụng chỉ nên áp dụng cho nhóm ảnh phù hợp. Có thể duy trì nhiều image family như `linux-base`, `linux-java`, `windows-base` hoặc `windows-app`, nhưng mỗi family cần có chủ sở hữu và tiêu chí hỗ trợ rõ ràng.

## 4. Xây dựng ảnh theo quy trình tự động và có thể tái tạo

Quy trình xây dựng ảnh nên chạy trong pipeline có kiểm soát. Công cụ có thể là Packer, image builder do nhà cung cấp đám mây cung cấp hoặc một hệ thống nội bộ. Dù dùng công cụ nào, các bước cần được mô tả bằng mã và lưu trong hệ thống quản lý phiên bản.

Một pipeline điển hình có các giai đoạn:

1. **Chọn ảnh nguồn:** lấy image gốc từ nguồn tin cậy, cố định phiên bản hoặc ID cụ thể thay vì tham chiếu một alias luôn thay đổi.
2. **Khởi tạo môi trường build:** tạo máy build tạm thời trong mạng và tài khoản có quyền tối thiểu.
3. **Cài đặt và cấu hình:** áp dụng bản vá, package, hardening, agent và cấu hình nền đã được phê duyệt.
4. **Làm sạch trạng thái:** xóa cache, file tạm, log build và dữ liệu nhận dạng tạm; bảo đảm không còn credential hay trạng thái của máy build.
5. **Tạo image artifact:** chụp ảnh máy từ trạng thái đã chuẩn hóa và gắn metadata về phiên bản, nguồn, thời gian, pipeline và chủ sở hữu.
6. **Kiểm thử:** khởi tạo máy từ ảnh vừa tạo, kiểm tra bảo mật, package, agent, khả năng boot và các chức năng vận hành.
7. **Phê duyệt và phát hành:** chỉ đưa ảnh qua kiểm thử vào danh mục được phép sử dụng.

Ví dụ dưới đây mô tả một pipeline ở mức khái niệm. Tên bước và cú pháp cần điều chỉnh theo công cụ CI/CD của tổ chức:

```yaml
stages:
  - build
  - harden
  - validate
  - publish

image_build:
  stage: build
  script:
    - select-approved-base-image
    - install-approved-packages
    - apply-os-baseline
    - install-monitoring-agent

image_validate:
  stage: validate
  script:
    - scan-image-for-vulnerabilities
    - verify-package-inventory
    - boot-test-created-image
    - verify-agent-registration

image_publish:
  stage: publish
  script:
    - attach-build-metadata
    - sign-image-artifact
    - publish-approved-version
```

Đây là ví dụ minh họa luồng công việc, không phải cấu hình có thể chạy trực tiếp. Trong triển khai thực tế, pipeline phải dùng cú pháp, runner, quyền truy cập và lệnh cụ thể của nền tảng đang sử dụng.

Để tăng khả năng tái tạo, cần cố định phiên bản package hoặc repository snapshot khi phù hợp, lưu mã cấu hình, ghi lại nguồn image và lưu kết quả build. Nếu cùng một commit và cùng bộ đầu vào tạo ra kết quả khác nhau, hãy điều tra thay đổi từ repository, package mirror, script tải xuống hoặc dịch vụ bên ngoài. Không nên dựa vào một image gốc không rõ nguồn gốc hoặc một script cài đặt không được kiểm soát.

## 5. Làm sạch ảnh và xử lý danh tính khi clone

Ảnh máy là bản chụp trạng thái của một hệ thống. Vì vậy, trước khi phát hành cần xem xét dữ liệu nào được giữ lại và dữ liệu nào phải xóa hoặc tạo lại. Đây là bước dễ bị bỏ qua nếu chỉ tập trung vào cài đặt package.

Các mục thường cần kiểm tra trước khi chụp ảnh:

- SSH host key trên Linux hoặc chứng thư định danh máy trên Windows phải được xử lý theo quy trình tạo mới khi clone.
- Machine ID và danh tính của agent quản trị, giám sát hoặc bảo mật phải được tái tạo hay đăng ký riêng cho từng instance.
- Xóa credential, token, file cấu hình tạm, khóa riêng, history của tài khoản build và file chứa dữ liệu nhạy cảm.
- Xóa cache package hoặc cache build nếu chúng chứa dữ liệu không cần thiết; giữ lại cache chỉ khi đã đánh giá lợi ích và rủi ro.
- Làm sạch log và file tạm của quá trình build để không đưa thông tin nội bộ vào ảnh.
- Đưa cloud-init hoặc công cụ bootstrap về trạng thái cho phép chạy lại ở máy mới.
- Kiểm tra các tác vụ tự khởi động không phụ thuộc vào hostname, địa chỉ IP hay danh tính của máy build.

Với Linux, có thể cần làm sạch machine ID, SSH host key và trạng thái cloud-init theo hướng dẫn của bản phân phối. Với Windows, quy trình Sysprep và generalized image thường được dùng để chuẩn bị hệ điều hành trước khi tạo ảnh dùng cho nhiều máy. Cách thực hiện phụ thuộc phiên bản hệ điều hành và nền tảng đám mây; cần kiểm thử sau khi clone để xác nhận hostname, SID hoặc thông tin nhận dạng liên quan, agent và dịch vụ khởi tạo hoạt động đúng.

Không nên tự động xóa mọi file nhận dạng theo một script chung mà không hiểu cơ chế của hệ điều hành. Hãy dùng phương pháp được nhà cung cấp hệ điều hành và nền tảng máy ảo hỗ trợ, sau đó kiểm thử nhiều lần tạo instance từ cùng một image để phát hiện danh tính trùng lặp.

## 6. Chọn thành phần dùng chung và quản lý phiên bản

Mỗi thành phần được đưa vào ảnh cần có lý do, chủ sở hữu và vòng đời cập nhật. Một bảng kiểm kê đơn giản giúp trả lời ảnh chứa gì và ai chịu trách nhiệm khi thành phần có lỗ hổng.

| Thành phần | Thông tin cần quản lý | Câu hỏi kiểm soát |
|---|---|---|
| Hệ điều hành | Distro/edition, phiên bản, kernel, ngày hết hỗ trợ | Còn được cập nhật bảo mật không? |
| Package hệ thống | Tên, phiên bản, repository và mục đích | Có thật sự cần cho mọi workload trong family không? |
| Runtime | Phiên bản, nhà cung cấp, chính sách hỗ trợ | Ứng dụng nào phụ thuộc vào phiên bản này? |
| Agent vận hành | Phiên bản, cấu hình mặc định, endpoint bootstrap | Agent có tự đăng ký danh tính mới khi clone không? |
| CA bundle | Nguồn phát hành, ngày hết hạn, quy trình xoay vòng | Có chứa chứng thư riêng hoặc CA không còn tin cậy không? |
| Baseline bảo mật | Phiên bản chính sách và kết quả kiểm tra | Quy tắc nào bắt buộc, quy tắc nào có ngoại lệ? |

Mỗi lần phát hành nên có một định danh không thay đổi, ví dụ `linux-base-2026.11.22.1`. Không ghi đè nội dung của một phiên bản ảnh đã phát hành. Nếu cần sửa package hoặc cấu hình, tạo phiên bản mới và lưu quan hệ với phiên bản nguồn.

Metadata của image có thể ghi các trường như:

```yaml
image_family: linux-base
image_version: 2026.11.22.1
os: ubuntu
os_release: "24.04"
build_commit: "a1b2c3d4"
source_image: "approved-base-image-id"
build_pipeline: "golden-image"
security_baseline: "baseline-3.2"
created_at: "2026-11-22T10:00:00Z"
```

Các giá trị trên chỉ là ví dụ minh họa. Metadata thật cần tuân theo quy ước đặt tên và trường dữ liệu của tổ chức. Không đưa secret hoặc thông tin nhạy cảm vào tag hay metadata vì những trường này thường hiển thị cho nhiều người có quyền đọc tài nguyên.

## 7. Kiểm thử chất lượng trước khi phát hành

Một image build thành công chưa chắc đã sẵn sàng sử dụng. Cần tạo máy thử từ image mới để kiểm tra hành vi sau khi clone, vì một số lỗi chỉ xuất hiện ở lần khởi động đầu tiên.

Các nhóm kiểm thử nên có:

| Nhóm kiểm thử | Nội dung kiểm tra | Kết quả mong đợi |
|---|---|---|
| Boot và bootstrap | Máy khởi động, cloud-init hoặc Sysprep hoàn tất, hostname và network được cấu hình | Instance sẵn sàng trong thời gian dự kiến |
| Package và phiên bản | Đối chiếu inventory với danh sách được duyệt | Không thiếu hoặc có package ngoài danh mục |
| Bảo mật | Quét lỗ hổng, kiểm tra hardening, quyền và dịch vụ mở | Đạt baseline hoặc có ngoại lệ được phê duyệt |
| Danh tính | Tạo nhiều instance từ cùng ảnh và so sánh machine/agent identity | Mỗi instance có danh tính riêng |
| Quan sát | Agent log, metric và inventory gửi dữ liệu đúng | Máy mới xuất hiện trong hệ thống giám sát |
| Vận hành | SSH/RDP quản trị, cập nhật cấu hình và khởi động lại | Quy trình quản trị hoạt động bình thường |
| Ứng dụng mẫu | Cài hoặc triển khai một workload đại diện | Runtime và thư viện nền tương thích |

Ngoài kiểm thử chức năng, nên kiểm tra thời gian khởi động, dung lượng ảnh, tốc độ tạo instance và mức sử dụng tài nguyên khi máy vừa boot. Một image quá lớn có thể làm tăng thời gian phân phối hoặc chi phí lưu trữ. Một agent khởi động quá nhiều tác vụ cùng lúc có thể làm máy mới chậm sẵn sàng.

Kết quả kiểm thử cần gắn với đúng image version và build ID. Nếu có lỗi, sửa pipeline hoặc cấu hình nguồn rồi tạo image version mới. Tránh sửa trực tiếp máy đã tạo từ ảnh để biến nó thành một image mới mà không ghi lại thay đổi, vì cách làm đó khiến kết quả khó tái tạo.

## 8. Phát hành, phân phối và sử dụng ảnh

Sau khi kiểm thử đạt yêu cầu, image được phát hành vào danh mục hoặc image registry được kiểm soát. Chỉ các nhóm hoặc pipeline có quyền phù hợp mới được tạo, sửa metadata hay chia sẻ ảnh. Quyền sử dụng ảnh cũng cần giới hạn theo tài khoản, dự án, vùng và môi trường.

Khi phân phối ảnh giữa các tài khoản hoặc vùng, kiểm tra chính sách chia sẻ, mã hóa, giấy phép hệ điều hành và các giới hạn của nền tảng. Không chia sẻ ảnh chứa dữ liệu nội bộ ngoài phạm vi được phép. Với image có dữ liệu nhạy cảm do yêu cầu nghiệp vụ, cần xem xét riêng quyền truy cập, mã hóa và quy trình thu hồi.

Hạ tầng nên tham chiếu một image version cụ thể hoặc một kênh phát hành được kiểm soát như `stable`. Không nên để workload production tự động lấy `latest` nếu alias này có thể đổi bất ngờ. Khi nâng cấp, triển khai image mới theo từng nhóm máy hoặc một đợt canary, theo dõi lỗi và khả năng phục vụ rồi mới mở rộng.

Một quy trình phát hành có thể gồm:

1. Pipeline tạo image mới và chạy toàn bộ kiểm thử.
2. Chủ sở hữu image phê duyệt phiên bản cùng kết quả scan.
3. Cập nhật image version trong cấu hình hạ tầng hoặc template triển khai.
4. Tạo một nhóm máy thử, xác nhận agent, ứng dụng và health check.
5. Mở rộng triển khai theo từng đợt và quan sát lỗi, độ trễ, hiệu năng.
6. Giữ lại image version trước trong thời gian rollback được quy định.

Rollback thường được thực hiện bằng cách triển khai lại máy từ image version đã biết là tốt, kết hợp với cấu hình ứng dụng tương thích. Không phải mọi thay đổi hệ điều hành đều có thể đảo ngược an toàn nếu ứng dụng hoặc dữ liệu đã thay đổi định dạng; cần kiểm tra tương thích trước khi phát hành.

## 9. Cập nhật và quản lý vòng đời golden image

Golden image có thể nhanh chóng lỗi thời nếu không có lịch cập nhật. Bản vá bảo mật, kernel, runtime, CA certificate và agent đều có thể thay đổi. Vì vậy, cần xác định chu kỳ build định kỳ và quy trình build khẩn cấp khi có lỗ hổng nghiêm trọng.

Một chính sách vòng đời nên xác định:

- **Tần suất build:** ví dụ build định kỳ hàng tháng và build ngoài chu kỳ khi có bản vá quan trọng.
- **Thời hạn xử lý lỗ hổng:** mức độ nghiêm trọng nào yêu cầu phát hành ảnh mới trong bao lâu.
- **Thời gian hỗ trợ:** ngày bắt đầu, ngày hết hỗ trợ của image family và hệ điều hành nền.
- **Thời gian lưu phiên bản cũ:** đủ lâu để rollback và đáp ứng yêu cầu kiểm toán, nhưng có giới hạn rõ ràng.
- **Thu hồi ảnh:** cách đánh dấu ảnh không còn được phép dùng, xử lý ảnh bị lỗi hoặc có lỗ hổng không thể khắc phục.
- **Chủ sở hữu:** người hoặc nhóm chịu trách nhiệm cập nhật, kiểm thử, phê duyệt và thông báo thay đổi.

Khi phát hiện một lỗ hổng trong package chung, cần xác định những image family và instance đang dùng phiên bản bị ảnh hưởng. Phát hành image đã vá chỉ xử lý các máy được tạo mới từ ảnh đó; những máy đang chạy vẫn cần được cập nhật theo quy trình patching hoặc thay thế bằng instance mới. Đây là điểm quan trọng trong mô hình immutable infrastructure: ảnh mới giúp chuẩn hóa máy được tạo sau này, còn fleet hiện tại cần một kế hoạch rollout riêng.

Nên theo dõi tỷ lệ máy đang chạy phiên bản ảnh được hỗ trợ, số máy dùng ảnh đã hết hạn và thời gian từ lúc phát hành ảnh mới đến khi fleet được cập nhật. Các chỉ số này cho biết quy trình golden image có thực sự cải thiện an toàn và tính nhất quán hay không.

## 10. Ví dụ thiết kế golden image cho nhóm máy chủ ứng dụng

Giả sử một tổ chức vận hành nhiều dịch vụ Java trên máy ảo Linux. Các nhóm ứng dụng dùng chung hệ điều hành, Java runtime cùng nhánh phiên bản, agent giám sát, agent bảo mật và CA bundle doanh nghiệp. Mỗi dịch vụ lại có endpoint, biến môi trường, quyền truy cập và phiên bản ứng dụng riêng.

Thiết kế có thể chia thành ba phần:

| Lớp | Nội dung | Cách quản lý |
|---|---|---|
| Golden image `linux-java-base` | Linux đã vá, hardening, Java runtime được duyệt, CA bundle, agent giám sát và bảo mật | Pipeline build và phát hành image theo version |
| Bootstrap của instance | Hostname, region, đăng ký agent, lấy cấu hình môi trường và secret theo danh tính máy | Cloud-init hoặc dịch vụ cấu hình khi boot |
| Triển khai ứng dụng | JAR/container workload, cấu hình dịch vụ, endpoint và phiên bản phát hành | Pipeline CI/CD của từng ứng dụng |

Khi nhóm A cần tạo máy mới, template hạ tầng tham chiếu `linux-java-base` version đã được phê duyệt. Khi máy khởi động, bootstrap tạo danh tính riêng, đăng ký agent và lấy cấu hình được cấp cho nhóm A. Pipeline ứng dụng triển khai artifact của nhóm A. Nhóm B có thể dùng cùng image version nhưng nhận cấu hình và artifact riêng theo quyền của nhóm B.

Khi có bản vá Java runtime, nhóm quản trị tạo image version mới, kiểm thử bằng workload đại diện của các nhóm ứng dụng rồi phát hành. Các dịch vụ lần lượt chuyển sang image mới theo kế hoạch. Nếu phát hiện lỗi tương thích, có thể dừng rollout và quay lại image version trước trong khi điều tra.

Thiết kế này giảm số bước cài đặt lặp lại, giúp các máy dùng cùng nền tảng và làm rõ trách nhiệm: nhóm nền tảng quản lý OS và thành phần dùng chung; nhóm ứng dụng quản lý artifact cùng cấu hình riêng; hệ thống secret manager quản lý thông tin nhạy cảm.

## 11. Những sai lầm thường gặp

- **Nhúng secret vào image:** mọi instance clone có thể mang theo cùng bí mật. Hãy cấp phát bí mật lúc chạy bằng danh tính workload.
- **Đưa cấu hình môi trường vào ảnh:** ảnh khó dùng lại giữa dev, staging và production. Hãy truyền cấu hình qua bootstrap hoặc config management.
- **Dùng image gốc thay đổi liên tục:** cùng một cấu hình build có thể tạo ra kết quả khác nhau ở các thời điểm khác nhau. Hãy cố định nguồn và phiên bản đầu vào.
- **Không làm sạch danh tính máy:** nhiều instance có thể dùng chung host key hoặc agent ID. Hãy kiểm thử quy trình clone và tạo danh tính mới.
- **Cài quá nhiều package:** ảnh lớn, nhiều lỗ hổng tiềm ẩn và khó cập nhật. Chỉ giữ thành phần có chủ sở hữu và nhu cầu rõ ràng.
- **Chỉ kiểm tra build thành công:** lỗi bootstrap hoặc agent có thể chỉ xuất hiện sau khi tạo instance. Hãy boot-test image thực tế.
- **Cập nhật ảnh nhưng bỏ quên máy đang chạy:** máy cũ vẫn có thể chứa lỗ hổng. Kết hợp phát hành ảnh với kế hoạch patch hoặc thay thế fleet.
- **Ghi đè image đã phát hành:** lịch sử khó kiểm toán và rollback không đáng tin cậy. Mỗi thay đổi cần tạo version mới.

## 12. Checklist trước khi phát hành

Trước khi đánh dấu một golden image là sẵn sàng, hãy xác nhận các điểm sau:

- [ ] Hệ điều hành còn được hỗ trợ và nguồn image gốc đáng tin cậy.
- [ ] Danh sách package, runtime, agent và CA bundle có phiên bản cùng chủ sở hữu rõ ràng.
- [ ] Baseline bảo mật được áp dụng và kiểm tra tự động.
- [ ] Không có secret, credential hoặc khóa riêng được nhúng trong image.
- [ ] Machine ID, host key và agent identity được tạo mới khi clone.
- [ ] Cloud-init, Sysprep hoặc cơ chế bootstrap đã được chuẩn bị đúng cho lần khởi động đầu.
- [ ] Image được boot-test và kiểm thử trên nhiều instance.
- [ ] Quét lỗ hổng, kiểm tra package inventory và lưu kết quả theo build ID.
- [ ] Metadata có version, nguồn, commit và thời điểm build.
- [ ] Image được phân quyền, phát hành và có quy trình rollback.
- [ ] Có lịch cập nhật, thời hạn hỗ trợ và quy trình thu hồi phiên bản lỗi thời.

Golden image chỉ có giá trị khi được duy trì như một sản phẩm nền tảng có chủ sở hữu, pipeline, kiểm thử và vòng đời rõ ràng. Khi thành phần dùng chung được chuẩn hóa và cấu hình riêng được cấp phát đúng thời điểm, tổ chức có thể tạo máy ảo nhất quán, rút ngắn thời gian triển khai và kiểm soát tốt hơn rủi ro vận hành.
