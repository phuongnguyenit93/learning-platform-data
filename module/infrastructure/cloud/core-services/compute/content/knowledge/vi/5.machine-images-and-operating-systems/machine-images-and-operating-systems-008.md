# Phân phối image qua nhiều region và nhiều tài khoản

Trong môi trường đám mây, một tổ chức thường vận hành ứng dụng ở nhiều region để giảm độ trễ, đáp ứng yêu cầu lưu trú dữ liệu hoặc duy trì khả năng khôi phục khi một khu vực gặp sự cố. Các nhóm phát triển, kiểm thử và production cũng thường nằm trong những tài khoản hoặc project riêng để phân tách quyền truy cập và chi phí. Khi đó, máy ảo ở các nơi cần một bộ image hệ điều hành và phần mềm nền đã được kiểm thử, cập nhật và quản lý nhất quán.

Phân phối image là quá trình đưa một phiên bản ảnh máy đã được chuẩn hóa đến các region và tài khoản đích, đồng thời bảo đảm quyền truy cập, mã hóa, khả năng khởi chạy và vòng đời của image. Bài học này trình bày cách thiết kế quy trình phân phối an toàn, có thể lặp lại và dễ kiểm soát khi số lượng region, tài khoản và phiên bản tăng lên.

## 1. Machine image là gì và vì sao cần phân phối?

Machine image là mẫu dùng để tạo máy ảo. Tùy nền tảng, image có thể bao gồm hệ điều hành, cấu trúc phân vùng, bootloader, driver, agent quản trị, thư viện và phần mềm đã cài đặt. Một image thường được tạo từ đĩa hệ thống hoặc từ một máy mẫu đã được chuẩn bị và chụp lại.

Cần phân biệt image với snapshot:

- **Image** mô tả một mẫu máy có thể dùng để tạo instance, thường bao gồm metadata về hệ điều hành, kiến trúc, chế độ khởi động và một hoặc nhiều đĩa.
- **Snapshot** là bản chụp dữ liệu của một volume hoặc đĩa tại một thời điểm. Snapshot có thể là thành phần nền của image.
- **Instance** là máy ảo đang chạy được tạo từ image và cấu hình tài nguyên cụ thể.

Một image có thể phụ thuộc vào nhiều snapshot, khóa mã hóa, quyền truy cập hoặc tài nguyên khác. Vì vậy, chỉ sao chép metadata image chưa chắc đã đủ để máy ảo ở nơi khác khởi chạy được.

### Vì sao cần phân phối image?

Các tình huống phổ biến gồm:

- Triển khai cùng một ứng dụng ở nhiều region để phục vụ người dùng gần hơn.
- Tạo môi trường development, testing, staging và production từ cùng một nền tảng đã kiểm thử.
- Phục hồi máy ảo khi region chính gặp sự cố.
- Chuẩn hóa image cho nhiều nhóm hoặc đơn vị kinh doanh.
- Đáp ứng yêu cầu kiểm toán, bảo mật và quản lý bản vá.
- Tạo máy mới nhanh hơn thay vì cài đặt hệ điều hành và phần mềm từ đầu.

Nếu mỗi region tự tạo image theo cách riêng, các máy có thể khác phiên bản package, agent bảo mật, cấu hình hệ điều hành hoặc bản vá. Sự khác biệt này làm tăng lỗi khó tái hiện và khiến việc điều tra sự cố phức tạp hơn.

Mục tiêu của phân phối image là đưa cùng một bản phát hành đã được kiểm thử đến đúng nơi cần dùng, có thể xác định nguồn gốc và quay lại phiên bản trước khi cần.

## 2. Region và account là hai phạm vi khác nhau

**Region** là khu vực địa lý nơi nhà cung cấp vận hành hạ tầng. Một số tài nguyên, trong đó có machine image hoặc snapshot trên nhiều nền tảng, có phạm vi theo region. Khi triển khai ở region khác, tổ chức có thể cần sao chép image hoặc tạo bản phân phối tại khu vực đó.

**Account, subscription hoặc project** là ranh giới quản lý tài nguyên, quyền truy cập, thanh toán và chính sách. Một image được tạo trong account trung tâm có thể cần được chia sẻ hoặc sao chép sang account của đội phát triển, đội vận hành hoặc môi trường production.

Hai chiều phân phối tạo thành ma trận:

| Chiều phân phối | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Giữa các region | Image đã có bản sẵn sàng ở khu vực triển khai chưa? | Từ region A sang region B và C |
| Giữa các account | Account đích có quyền sử dụng image chưa? | Từ account xây dựng sang account staging và production |
| Giữa region và account | Bản image nào thuộc account nào tại từng region? | Bản sao ở region B trong account production |

Không nên giả định image có cùng phạm vi ở mọi nhà cung cấp. Có nền tảng quản lý image theo region, có nền tảng cung cấp thư viện image tập trung rồi nhân bản phiên bản đến nhiều region, và có nền tảng cho phép chia sẻ image ở phạm vi project hoặc tổ chức. Cần kiểm tra tài liệu và giới hạn của đúng dịch vụ đang sử dụng.

## 3. Chia sẻ, sao chép và xuất/nhập image

Có ba cách phổ biến để đưa image đến nơi khác. Mỗi cách có quyền sở hữu và vòng đời khác nhau.

| Phương thức | Cách hoạt động | Ưu điểm | Điểm cần cân nhắc |
|---|---|---|---|
| Chia sẻ (share) | Cấp quyền cho account hoặc nhóm đích sử dụng image nguồn | Nhanh, giảm số bản sao và có thể tiết kiệm lưu trữ | Account nguồn vẫn quản lý image; quyền có thể bị thu hồi; phụ thuộc quyền snapshot và khóa |
| Sao chép (copy) | Tạo image độc lập ở region hoặc account đích | Account đích có thể quản lý vòng đời riêng; thuận tiện cho DR và kiểm soát phát hành | Tốn thời gian, dung lượng và chi phí truyền dữ liệu; cần xử lý mã hóa |
| Xuất/nhập (export/import) | Xuất image thành định dạng trung gian rồi nhập vào nền tảng hoặc môi trường khác | Có thể hỗ trợ di chuyển giữa nền tảng nếu định dạng tương thích | Có thể mất metadata, cần chuyển đổi định dạng, kiểm tra driver, boot và giấy phép |

### Chia sẻ image

Chia sẻ phù hợp khi nhiều account cần sử dụng một image chuẩn do nhóm nền tảng quản lý. Account đích được cấp quyền khởi tạo máy hoặc truy cập image theo cơ chế của nhà cung cấp.

Khi chia sẻ, cần kiểm tra toàn bộ phụ thuộc:

- Quyền sử dụng image.
- Quyền đọc hoặc sử dụng các snapshot tạo nên image.
- Quyền sử dụng khóa mã hóa nếu snapshot được mã hóa.
- Quyền tạo instance và sử dụng loại máy tương ứng ở account đích.
- Các điều kiện tổ chức, policy hoặc giới hạn marketplace.

Một image có thể xuất hiện trong danh sách tài nguyên của account đích nhưng vẫn không khởi chạy được nếu snapshot hoặc khóa mã hóa chưa được cấp quyền.

Chia sẻ cũng tạo ra phụ thuộc vòng đời. Nếu account nguồn xóa image, thu hồi quyền hoặc thay đổi khóa, account đích có thể không còn khởi chạy được máy mới. Các instance đang chạy có thể chịu tác động khác nhau tùy nền tảng, nhưng không nên dựa vào giả định rằng quyền chia sẻ luôn được giữ nguyên.

### Sao chép image

Sao chép tạo ra bản image độc lập ở đích. Cách này thường phù hợp với production, môi trường khôi phục thảm họa hoặc tổ chức muốn account đích tự quản lý quyền và vòng đời.

Bản sao có thể cần:

1. Đọc image và snapshot nguồn.
2. Truyền dữ liệu đến region đích.
3. Tạo snapshot hoặc đĩa tương ứng ở đích.
4. Mã hóa lại bằng khóa được phép dùng tại đích.
5. Tạo metadata image mới.
6. Kiểm tra trạng thái hoàn tất và khả năng khởi chạy.

Sao chép có thể mất thời gian tùy dung lượng đĩa, tải nền tảng và số lượng bản sao. Pipeline cần theo dõi trạng thái, retry khi lỗi tạm thời và tránh tạo nhiều bản trùng do chạy lại cùng một yêu cầu.

### Xuất và nhập image

Xuất/nhập hữu ích khi di chuyển giữa nhà cung cấp hoặc từ môi trường on-premises lên cloud. Tuy nhiên, image có thể phụ thuộc driver, firmware, định dạng đĩa, boot mode, license và công cụ quản trị riêng.

Sau khi nhập, cần kiểm tra lại:

- BIOS hay UEFI và cấu hình Secure Boot.
- Kiến trúc CPU x86-64 hay Arm.
- Driver lưu trữ và mạng.
- Bootloader, kernel và initramfs.
- Cấu trúc phân vùng, filesystem và dung lượng đĩa.
- Agent quản trị, cloud-init hoặc công cụ khởi tạo tương đương.
- License và quyền sử dụng hệ điều hành/phần mềm.

Không xem thao tác import thành công là bằng chứng image đã sẵn sàng cho production. Phải khởi chạy thử và xác minh dịch vụ hoạt động.

## 4. Kiến trúc phân phối tập trung

Một mô hình thường dùng là xây dựng image trong account hoặc project chuyên trách, sau đó phân phối phiên bản đã duyệt tới các account và region tiêu thụ.

~~~mermaid
flowchart TD
    A["Base OS và cấu hình chuẩn"] --> B["Image factory: build và generalize"]
    B --> C["Quét lỗ hổng, kiểm tra và ký metadata"]
    C --> D{"Đạt tiêu chí phát hành?"}
    D -- "Không" --> E["Sửa image và build phiên bản mới"]
    E --> B
    D -- "Có" --> F["Phê duyệt phiên bản"]
    F --> G["Phân phối đến các region"]
    G --> H["Chia sẻ hoặc copy sang account đích"]
    H --> I["Kiểm tra quyền, khóa và phụ thuộc"]
    I --> J["Khởi chạy thử tại đích"]
    J --> K{"Smoke test đạt?"}
    K -- "Không" --> L["Dừng phát hành và điều tra"]
    K -- "Có" --> M["Đánh dấu phiên bản được phép sử dụng"]
    M --> N["Triển khai VM và theo dõi"]
~~~

### Vai trò của image factory

Image factory là quy trình hoặc hệ thống chịu trách nhiệm tạo image chuẩn. Nó có thể dùng dịch vụ image builder của nhà cung cấp, công cụ như Packer hoặc pipeline CI/CD.

Image factory nên quản lý:

- Phiên bản hệ điều hành gốc và nguồn image.
- Danh sách package, agent và cấu hình bảo mật.
- Quy trình cập nhật bản vá.
- Cấu hình khởi tạo để image có thể dùng lại.
- Quét lỗ hổng và kiểm tra tuân thủ.
- Metadata, SBOM hoặc thông tin nguồn gốc nếu tổ chức yêu cầu.
- Phiên bản phát hành và danh sách đích đã phân phối.

Account xây dựng image thường có quyền rộng hơn account tiêu thụ. Cần bảo vệ pipeline, thông tin xác thực và quyền tạo image vì một image bị can thiệp có thể ảnh hưởng đến nhiều hệ thống.

### Tách build, distribution và consumption

Nên phân tách ba vai trò:

- **Build:** tạo và kiểm tra image.
- **Distribution:** sao chép hoặc chia sẻ image, quản lý quyền và khóa.
- **Consumption:** sử dụng image đã được duyệt để tạo máy.

Phân tách giúp giảm quyền của account triển khai. Đội ứng dụng có thể được phép chọn image trong danh sách đã phê duyệt nhưng không có quyền sửa nội dung image chuẩn hoặc cấp quyền chia sẻ ra bên ngoài tổ chức.

## 5. Chuẩn bị image trước khi phân phối

Phân phối chỉ đáng tin cậy khi image nguồn đã được chuẩn hóa. Một image được tạo trực tiếp từ máy đang chạy có thể mang theo trạng thái riêng của máy đó.

### Generalize hệ điều hành

Trước khi capture, cần đưa hệ điều hành về trạng thái có thể khởi tạo độc lập cho nhiều instance. Quy trình tùy hệ điều hành và công cụ:

- Linux thường cần làm sạch trạng thái cloud-init, log tạm, cache package và định danh máy được tạo khi boot.
- Windows thường dùng quy trình generalize như Sysprep theo hướng dẫn của hệ điều hành và nhà cung cấp.
- Host key SSH, machine identity và các thông tin nhận dạng riêng cần được tạo mới ở lần khởi động đầu nếu phù hợp.
- Agent quản trị cần được cấu hình để đăng ký instance mới đúng cách.
- Dịch vụ tự khởi động cần tránh giữ trạng thái phiên hoặc dữ liệu riêng của máy mẫu.

Không xóa tùy tiện dữ liệu hệ thống cần thiết để boot. Hãy dùng quy trình capture được nhà cung cấp và hệ điều hành hỗ trợ.

### Không nhúng bí mật vào image

Không đưa các nội dung sau vào image chuẩn:

- Password, private key hoặc access token.
- Credential của tài khoản dịch vụ.
- Chứng thư riêng gắn với một máy hoặc một môi trường.
- File cấu hình chứa khóa truy cập database.
- Dữ liệu khách hàng, log nhạy cảm hoặc dump bộ nhớ.
- Thông tin định danh môi trường production.

Hãy lấy bí mật khi instance khởi động thông qua secret manager hoặc cơ chế cấp phát danh tính máy. Quyền lấy secret phải giới hạn theo vai trò và môi trường.

### Chuẩn hóa cấu hình có thể tái sử dụng

Image có thể chứa agent giám sát, agent bảo mật, runtime, thư viện và package chung. Các thông tin thay đổi theo region hoặc account nên được cấu hình khi boot hoặc qua công cụ quản lý cấu hình.

Ví dụ, hostname, endpoint nội bộ, địa chỉ proxy, vùng lưu log và role của máy không nên cố định trong image dùng cho nhiều môi trường.

## 6. Mã hóa image và quản lý khóa khi phân phối

Image và snapshot thường chứa toàn bộ nội dung đĩa hệ thống, bao gồm cấu hình, log và dữ liệu ứng dụng. Cần mã hóa dữ liệu lưu trữ và kiểm soát quyền dùng khóa.

### Vì sao cần chú ý khóa mã hóa?

Khóa do dịch vụ quản lý khóa (KMS hoặc dịch vụ tương đương) có thể được giới hạn theo region, account hoặc policy. Khóa ở region nguồn không nhất thiết dùng được tại region đích. Một account có quyền đọc image cũng không tự động có quyền giải mã snapshot.

Khi phân phối image mã hóa, cần xác định:

1. Image nguồn dùng khóa do nhà cung cấp quản lý hay khóa do tổ chức quản lý.
2. Account và dịch vụ nào được phép dùng khóa nguồn.
3. Region đích có khóa tương thích và được cấp quyền hay không.
4. Bản sao có cần mã hóa lại bằng khóa riêng của account đích không.
5. Ai được phép tạo grant, thay đổi key policy hoặc vô hiệu hóa khóa.
6. Quy trình thu hồi quyền và xử lý khi khóa hết hạn hoặc bị vô hiệu hóa.

### Mô hình khóa ở account đích

Một mô hình thường dùng là account image factory mã hóa image nguồn, sau đó account đích sao chép và mã hóa lại bằng khóa do chính account đích quản lý. Cách này giảm phụ thuộc lâu dài vào khóa nguồn và cho phép từng môi trường kiểm soát quyền giải mã.

Ví dụ luồng xử lý:

~~~text
Image nguồn
  -> Account nguồn cấp quyền đọc image/snapshot và dùng khóa nguồn
  -> Sao chép sang region/account đích
  -> Tạo snapshot đích và mã hóa bằng khóa đích
  -> Tạo image đích
  -> Kiểm tra quyền khởi chạy và thử boot
~~~

Tên thao tác và khả năng mã hóa lại phụ thuộc nền tảng. Một số dịch vụ yêu cầu cấp quyền khóa trước khi copy; một số dịch vụ cho phép chỉ định khóa đích ngay trong thao tác sao chép.

### Nguyên tắc quản lý khóa

- Dùng khóa theo môi trường hoặc theo miền tin cậy khi cần tách quyền.
- Cấp quyền tối thiểu cho dịch vụ sao chép và vai trò triển khai.
- Theo dõi việc sử dụng khóa bằng audit log.
- Không chia sẻ quyền quản trị khóa rộng hơn quyền cần để đọc hoặc sao chép image.
- Lập kế hoạch luân chuyển, vô hiệu hóa và khôi phục khóa.
- Kiểm tra lại image sau khi đổi khóa hoặc thay đổi key policy.

Nếu khóa nguồn bị vô hiệu hóa trước khi bản sao đích hoàn tất và được kiểm tra, pipeline có thể thất bại hoặc image không còn sử dụng được. Không xóa khóa chỉ vì image đã được copy; trước hết cần xác minh snapshot đích độc lập và chính sách lưu giữ.

## 7. Cấp quyền chia sẻ an toàn giữa các account

### Chỉ chia sẻ cho đúng đối tượng

Nên xác định rõ account hoặc nhóm nào được sử dụng image. Tùy nền tảng, quyền có thể được cấp qua resource policy, IAM, RBAC, tổ chức hoặc cơ chế chia sẻ thư viện image.

Không chia sẻ image công khai nếu không có lý do rõ ràng và quy trình phê duyệt. Image có thể chứa cấu hình nội bộ, package độc quyền hoặc dấu vết thông tin nhạy cảm.

### Quyền image có thể khác quyền snapshot và khóa

Một số nền tảng quản lý image và snapshot thành các tài nguyên có quyền riêng. Vì thế, checklist cấp quyền cần bao gồm:

| Thành phần | Quyền cần xác minh |
|---|---|
| Image | Account đích có được xem, chọn hoặc tạo instance từ image không? |
| Snapshot/đĩa nền | Dịch vụ có thể đọc các thành phần tạo nên image không? |
| Khóa mã hóa | Vai trò hoặc dịch vụ đích có quyền sử dụng khóa để giải mã/copy không? |
| Compute | Account đích có quota và quyền tạo loại VM cần thiết không? |
| Network | Instance có thể gắn vào subnet, security group hoặc network đích không? |

Cấp quyền image thành công không đồng nghĩa các quyền phụ thuộc đã đầy đủ.

### Tách quyền đọc và quyền phát hành

Vai trò tiêu thụ thường chỉ cần quyền đọc image đã duyệt và tạo máy. Quyền tạo image, sửa quyền chia sẻ, thay đổi khóa hoặc xóa image nên thuộc nhóm nền tảng được kiểm soát.

Với môi trường production, có thể yêu cầu quy trình phê duyệt trước khi đưa một phiên bản mới vào danh sách image được phép dùng. Audit log cần ghi nhận ai tạo, ai phê duyệt, ai phân phối và account nào đã sử dụng phiên bản đó.

## 8. Phân phối qua nhiều region

### Tạo bản sao theo region

Nếu image có phạm vi region, pipeline cần tạo bản tương ứng tại mỗi khu vực. Quy trình tổng quát:

1. Xác định region nguồn và image phiên bản đã duyệt.
2. Kiểm tra region đích có hỗ trợ hệ điều hành, kiến trúc và loại máy cần dùng.
3. Xác minh quota, quyền truy cập snapshot và khóa.
4. Bắt đầu sao chép image.
5. Theo dõi trạng thái đến khi hoàn tất.
6. Kiểm tra metadata, mã hóa và các phụ thuộc.
7. Khởi chạy máy thử trong region đích.
8. Chỉ đánh dấu image sẵn sàng sau khi smoke test đạt.

Không nên coi lệnh copy trả về mã yêu cầu là bằng chứng bản sao đã sẵn sàng. Nhiều dịch vụ xử lý sao chép bất đồng bộ; cần đợi trạng thái cuối cùng.

### Lưu ý về khả năng cung cấp tài nguyên

Một image có thể tồn tại ở region đích nhưng loại VM hoặc GPU mà ứng dụng cần lại không khả dụng ở đó. Cần xác minh:

- Kiến trúc CPU và thế hệ instance được hỗ trợ.
- Chế độ boot, Secure Boot và tính năng bảo mật.
- Driver GPU, thiết bị tăng tốc hoặc driver mạng.
- Loại volume và giới hạn IOPS/throughput.
- Quota của instance, GPU, snapshot và image.
- Khả năng tạo máy ở vùng sẵn sàng cần thiết.

Nếu image dùng driver hoặc cấu hình riêng cho một loại phần cứng, cần kiểm thử trên loại máy đại diện tại từng region.

### Độ trễ và chi phí phân phối

Sao chép image dung lượng lớn qua nhiều region có thể phát sinh phí truyền dữ liệu, snapshot và lưu trữ. Nếu mỗi lần build đều tạo bản sao đầy đủ ở mọi nơi, chi phí và thời gian phân phối sẽ tăng.

Có thể tối ưu bằng cách:

- Chỉ phân phối phiên bản được phê duyệt.
- Xóa hoặc lưu trữ phiên bản cũ theo chính sách.
- Dùng lịch phân phối phù hợp với cửa sổ bảo trì.
- Ưu tiên region cần triển khai trước.
- Theo dõi dung lượng snapshot và chi phí lưu trữ.
- Tránh copy lặp lại khi image và nội dung không thay đổi.

## 9. Phân phối qua nhiều account

### Mô hình account trung tâm

Một tổ chức có thể dùng account riêng cho image factory, sau đó phân phối image tới các account ứng dụng:

| Account | Vai trò | Quyền phù hợp |
|---|---|---|
| Image factory | Build, scan, test và phát hành image | Quyền tạo image, quản lý phiên bản và phân phối |
| Development | Thử nghiệm ứng dụng trên image mới | Quyền đọc image và tạo VM trong quota được cấp |
| Staging | Kiểm thử trước production | Quyền dùng image đã được duyệt cho kiểm thử |
| Production | Chạy dịch vụ thực tế | Quyền dùng image trong kênh phát hành production |
| Disaster recovery | Duy trì khả năng khôi phục ở region/account dự phòng | Quyền dùng image dự phòng và tài nguyên phục hồi |

Account factory không nên dùng chung credential quản trị với account ứng dụng. Nên dùng role hoặc service identity riêng cho từng thao tác, có thời hạn và quyền tối thiểu.

### Share hay copy sang account đích?

Chọn chia sẻ khi account đích chỉ cần dùng image và tổ chức muốn duy trì một nguồn quản lý tập trung. Chọn copy khi account đích cần độc lập về vòng đời, khóa mã hóa, quyền truy cập hoặc khả năng khôi phục.

Với production và disaster recovery, bản sao độc lập thường giúp giảm phụ thuộc vào account nguồn. Tuy nhiên, cần kiểm tra quy trình cập nhật và thu hồi phiên bản để tránh các account đích tiếp tục dùng image đã lỗi thời.

### Account khác tổ chức hoặc tenant

Chia sẻ ra ngoài tổ chức có rủi ro cao hơn vì khó kiểm soát danh tính, chính sách và vòng đời. Trước khi thực hiện, cần xác minh:

- Bên nhận có nằm trong danh sách tổ chức được phê duyệt không?
- Dữ liệu hoặc package trong image có được phép chuyển giao không?
- Có điều khoản license giới hạn việc chia sẻ không?
- Khóa mã hóa có thể được sử dụng theo chính sách không?
- Có yêu cầu hợp đồng, lưu trú dữ liệu hoặc kiểm toán không?
- Khi kết thúc hợp tác, quyền và bản sao image được thu hồi thế nào?

Không dùng quyền chia sẻ rộng hoặc public để giải quyết nhanh lỗi truy cập. Hãy xác định chính xác thành phần nào đang thiếu quyền.

## 10. Quản lý phiên bản và tính nhất quán

### Mỗi image phát hành cần có định danh rõ ràng

Image nên có tên và phiên bản có thể truy vết, ví dụ:

~~~text
web-api-linux-2026.11.22.1
web-api-linux-2026.12.05.1
worker-linux-2026.12.05.2
~~~

Tên phiên bản có thể chứa ứng dụng, hệ điều hành, ngày build và số lần phát hành. Không dùng tên chung như latest làm định danh duy nhất vì nó có thể trỏ sang phiên bản khác theo thời gian.

Mỗi lần thay đổi package, bản vá hoặc cấu hình bảo mật nên tạo phiên bản mới. Không chỉnh sửa nội dung của image đã phát hành theo cách khiến cùng một ID mang ý nghĩa khác nhau.

### Manifest phân phối

Nên lưu manifest hoặc bản ghi phát hành cho mỗi phiên bản. Ví dụ cấu trúc minh họa:

~~~yaml
image:
  name: web-api-linux
  version: "2026.11.22.1"
  source:
    account: image-factory
    region: region-a
    image_id: image-source-id
  properties:
    os: linux
    architecture: x86_64
    boot_mode: uefi
    encrypted: true
  release:
    build_id: build-1042
    approved: true
    scan_status: passed
  targets:
    - account: staging
      region: region-b
      distribution: copy
      status: ready
      image_id: image-staging-id
    - account: production
      region: region-c
      distribution: copy
      status: ready
      image_id: image-production-id
~~~

Các ID trong ví dụ chỉ là giá trị minh họa. Manifest thực tế cần lưu định danh tài nguyên do nền tảng trả về, trạng thái phân phối, khóa đích, thời điểm hoàn tất và kết quả kiểm thử.

### Dùng cùng một bản phát hành đã kiểm thử

Khi image được phê duyệt, phân phối chính phiên bản đó tới các đích. Không build lại một image riêng tại mỗi region chỉ vì cần cùng tên. Build độc lập có thể tạo ra khác biệt package, thời gian cập nhật hoặc cấu hình.

Nếu mỗi region bắt buộc phải có cấu hình riêng, hãy giữ phần khác biệt ở bước boot hoặc cấu hình runtime. Metadata của image và manifest cần chỉ rõ phiên bản nguồn chung để có thể truy vết.

### Kênh phát hành và alias

Có thể dùng các kênh như development, candidate, stable hoặc production để xác định image được phép sử dụng. Alias như stable hoặc latest là con trỏ có thể thay đổi; pipeline cần ghi lại image ID/version thực tế mà mỗi lần triển khai đã sử dụng.

Với hệ thống cần tái tạo chính xác, hãy ghim deployment vào ID hoặc version cụ thể thay vì chỉ tham chiếu alias.

## 11. Tự động hóa pipeline phân phối

Một pipeline phân phối image có thể được triển khai bằng CI/CD, dịch vụ image builder và các API quản lý tài nguyên của nhà cung cấp.

Các giai đoạn nên có:

1. **Build:** tạo image từ base image đã được phê duyệt.
2. **Generalize:** làm sạch định danh và trạng thái riêng của máy mẫu.
3. **Scan:** quét lỗ hổng, kiểm tra package và baseline bảo mật.
4. **Test:** khởi chạy thử, kiểm tra boot, agent và dịch vụ cơ bản.
5. **Approve:** người hoặc policy có thẩm quyền phê duyệt phát hành.
6. **Distribute:** share hoặc copy đến các region/account đích.
7. **Verify:** kiểm tra trạng thái, khóa, quyền, snapshot và metadata.
8. **Smoke test:** tạo máy thử tại đích, xác minh boot và health check.
9. **Publish:** đánh dấu phiên bản sẵn sàng cho deployment.
10. **Retain:** lưu phiên bản trước và xóa phiên bản hết hạn theo chính sách.

### Xử lý lỗi và retry

Sao chép có thể thất bại do quota, quyền khóa, giới hạn API, thiếu dung lượng hoặc region không hỗ trợ. Pipeline cần phân biệt lỗi tạm thời và lỗi cấu hình.

- Với lỗi tạm thời như throttling hoặc timeout, retry có backoff và giới hạn số lần.
- Với lỗi quyền hoặc khóa, dừng và yêu cầu sửa policy; không retry vô hạn.
- Với lỗi quota, ghi nhận region/account bị ảnh hưởng và xử lý quota trước khi chạy lại.
- Với lỗi smoke test, giữ image ở trạng thái chưa được phát hành.
- Với thao tác bất đồng bộ, theo dõi trạng thái theo operation ID hoặc resource ID.

Pipeline phải idempotent. Nếu chạy lại cùng phiên bản, cần kiểm tra bản sao đã tồn tại và trạng thái của nó trước khi tạo mới. Dùng tên phiên bản, build ID hoặc tag làm khóa nhận dạng để tránh phát sinh nhiều image trùng lặp.

### Ví dụ cấu trúc pipeline

~~~yaml
stages:
  - build
  - generalize
  - scan
  - test
  - approve
  - distribute
  - verify
  - publish

distribution:
  source_account: image-factory
  source_region: region-a
  image_version: "2026.11.22.1"
  targets:
    - account: staging
      regions:
        - region-b
    - account: production
      regions:
        - region-b
        - region-c
  encryption:
    reencrypt_at_destination: true
  verification:
    boot_test: true
    security_scan: true
    application_health_check: true
~~~

Đây là cấu trúc minh họa để mô tả ý tưởng. Cú pháp pipeline và tên trường phụ thuộc công cụ CI/CD và nhà cung cấp cloud.

## 12. Kiểm thử image tại region và account đích

Image chỉ nên được công bố sau khi kiểm tra được ở môi trường đích. Kiểm thử tại nguồn không bảo đảm máy sẽ boot thành công ở region hoặc account khác.

### Kiểm tra trước khi tạo VM

- Image ID và version đúng với manifest.
- Image ở trạng thái sẵn sàng.
- Account đích có quyền sử dụng image và snapshot.
- Khóa mã hóa đích còn hoạt động và được cấp quyền.
- Kiến trúc CPU, boot mode và loại instance tương thích.
- Quota và dung lượng máy ở region đích đủ.
- Network, subnet và security policy có thể tạo máy.
- License và điều khoản sử dụng hợp lệ.

### Smoke test sau khi khởi chạy

Một máy thử ở mỗi nhóm đích nên kiểm tra:

- Hệ điều hành boot hoàn tất.
- Disk được nhận diện và mount đúng.
- Network interface nhận cấu hình đúng.
- Agent giám sát và bảo mật đăng ký thành công.
- Cloud-init hoặc công cụ khởi tạo hoàn tất.
- Không còn hostname, host key hoặc machine ID bị trùng.
- Ứng dụng hoặc dịch vụ nền khởi động được.
- Log được gửi tới hệ thống đích.
- Instance có thể truy cập các dịch vụ cần thiết bằng danh tính và quyền được cấp.

Nếu các region có phần cứng hoặc policy khác nhau, cần kiểm thử theo từng nhóm cấu hình thay vì chỉ thử một máy đại diện cho toàn bộ hệ thống.

### Kiểm tra sau khi triển khai thật

Theo dõi tỷ lệ boot thành công, thời gian khởi động, lỗi agent, lỗi mount, lỗi network và lỗi ứng dụng. So sánh với phiên bản trước để phát hiện regression. Nếu image mới làm tăng thời gian khởi động hoặc gây lỗi, dừng rollout và quay lại phiên bản ổn định.

## 13. Cập nhật, thu hồi và rollback

### Cập nhật bản vá

Image cần được cập nhật định kỳ theo lịch và theo mức độ nghiêm trọng của lỗ hổng. Quy trình nên bao gồm:

- Xác định base image và package cần cập nhật.
- Build phiên bản mới.
- Quét lỗ hổng và kiểm tra cấu hình.
- Chạy kiểm thử khởi động và ứng dụng.
- Phân phối tới các đích.
- Canary trên một nhóm nhỏ trước khi rollout rộng.
- Theo dõi lỗi và phê duyệt mở rộng.

Không nên chỉ cập nhật image ở region chính rồi để các region còn lại dùng bản cũ trong thời gian không xác định. Manifest phải thể hiện region/account nào đã nhận phiên bản mới.

### Rollback

Giữ lại ít nhất một phiên bản ổn định trước đó trong thời gian phù hợp với yêu cầu vận hành. Khi image mới gặp lỗi:

1. Dừng phân phối hoặc rollout tiếp.
2. Xác định các account và region đã dùng phiên bản lỗi.
3. Chuyển kênh phát hành về image ổn định trước đó.
4. Tạo máy mới từ phiên bản cũ hoặc thay đổi launch template theo quy trình.
5. Kiểm tra dịch vụ và dữ liệu sau khi phục hồi.
6. Ghi nhận nguyên nhân và cập nhật pipeline kiểm thử.

Rollback image không tự động đưa các máy đang chạy về trạng thái cũ. Có thể cần thay thế instance, cập nhật template hoặc triển khai lại workload. Dữ liệu ứng dụng phải được lưu trên dịch vụ lưu trữ phù hợp để việc thay máy không làm mất dữ liệu.

### Ngừng sử dụng image cũ

Trước khi xóa image, cần xác định có launch template, autoscaling group, deployment template, VM hoặc quy trình khôi phục nào còn tham chiếu đến nó không. Một image không còn được dùng để tạo máy mới vẫn có thể cần thiết cho khôi phục hoặc kiểm toán.

Nên có các trạng thái vòng đời:

- Draft: đang xây dựng.
- Tested: đã qua kiểm thử kỹ thuật.
- Approved: được phép phát hành.
- Distributed: đã có ở các đích yêu cầu.
- Deprecated: không dùng cho triển khai mới.
- Retired: đã ngừng hỗ trợ và đủ điều kiện xóa theo chính sách.

## 14. Khác biệt giữa các nền tảng cloud

Các khái niệm chung giống nhau nhưng cách triển khai cụ thể khác nhau:

| Nền tảng | Cơ chế thường gặp | Điểm cần xác minh |
|---|---|---|
| AWS | AMI, snapshot EBS, chia sẻ launch permission và copy AMI giữa region | Quyền snapshot, quyền KMS, mã hóa lại và phạm vi AMI theo region |
| Microsoft Azure | Azure Compute Gallery và image version được nhân bản đến các region | Replica count, RBAC, subscription/tenant sharing, quota và trạng thái replication |
| Google Cloud | Custom image, project IAM và các cơ chế image/snapshot của Compute Engine | Phạm vi tài nguyên, quyền project, mã hóa, image family và khả năng dùng tại project đích |

Bảng trên mô tả các cơ chế phổ biến ở mức khái niệm; tên tính năng, giới hạn và khả năng chia sẻ có thể thay đổi theo dịch vụ và thời điểm. Cần kiểm tra tài liệu hiện hành của nền tảng trước khi viết automation hoặc policy.

### AWS

AMI thường gắn với region và có thể được copy sang region khác. Việc chia sẻ AMI có thể cần chia sẻ quyền sử dụng các snapshot nền. Nếu snapshot được mã hóa bằng customer-managed KMS key, cần cấp quyền thích hợp cho thao tác chia sẻ/copy và có thể mã hóa lại bằng khóa ở đích.

### Azure

Azure Compute Gallery hỗ trợ quản lý image version và phân phối replica tới các region. Quyền truy cập được quản lý qua cơ chế kiểm soát truy cập của Azure. Cần kiểm tra cách chia sẻ giữa subscription hoặc tenant, trạng thái replication, quota và cấu hình phiên bản.

### Google Cloud

Compute Engine hỗ trợ custom image và quyền truy cập ở cấp project thông qua IAM. Image có thể được dùng bởi các project khác nếu quyền và phạm vi tài nguyên cho phép. Cần kiểm tra cách image được lưu trữ, khóa mã hóa, chính sách organization và khả năng khởi chạy ở project đích.

## 15. Ví dụ: phân phối image cho hệ thống nhiều region

Một tổ chức vận hành dịch vụ web tại ba region và chia tài nguyên thành bốn account: image factory, development, production và disaster recovery.

Nhóm nền tảng xây dựng image Linux đã cài runtime, agent bảo mật và agent giám sát trong image factory. Sau khi scan và smoke test ở region nguồn, nhóm phê duyệt phiên bản 2026.11.22.1.

Quy trình phân phối:

1. Tạo bản sao ở region phục vụ development và chạy kiểm thử tích hợp.
2. Khi kiểm thử đạt, copy phiên bản đó sang account production tại các region vận hành.
3. Mỗi account đích mã hóa bản sao bằng khóa do account đó quản lý.
4. Tạo bản sao ở region dự phòng trong account disaster recovery.
5. Chạy smoke test ở từng nhóm region/account và lưu image ID vào manifest.
6. Đánh dấu phiên bản được phép sử dụng cho deployment.
7. Giữ phiên bản trước đó để rollback trong thời gian quy định.

| Đích | Phương thức | Kiểm tra quan trọng |
|---|---|---|
| Development | Copy hoặc share tùy chính sách | Boot, agent, kiểm thử ứng dụng |
| Production region A | Copy và mã hóa bằng khóa đích | Quyền, quota, health check |
| Production region B | Copy và mã hóa bằng khóa đích | Tương thích instance và network |
| Disaster recovery region C | Copy độc lập | Khả năng tạo VM khi account nguồn không khả dụng |

Nếu account image factory tạm thời không hoạt động, các account production và DR vẫn có thể dùng image đã sao chép và khóa đích của mình để tạo máy mới. Khả năng này phải được kiểm thử định kỳ; chỉ có bản sao image mà thiếu quota, quyền hoặc khóa hợp lệ vẫn chưa đủ để khôi phục.

## 16. Checklist phân phối image

- [ ] Image nguồn đã được chuẩn hóa và generalize.
- [ ] Image không chứa password, token, private key hoặc dữ liệu nhạy cảm.
- [ ] Đã xác định chính xác version, build ID và nguồn gốc image.
- [ ] Đã quét lỗ hổng và kiểm tra baseline bảo mật.
- [ ] Đã xác minh license và quyền sử dụng hệ điều hành/phần mềm.
- [ ] Đã chọn rõ share, copy hay export/import cho từng đích.
- [ ] Đã kiểm tra quyền image, snapshot và khóa mã hóa.
- [ ] Đã có khóa đích và quy trình mã hóa lại nếu cần.
- [ ] Đã xác minh quota, khả năng cung cấp instance và hỗ trợ region.
- [ ] Đã kiểm tra kiến trúc CPU, boot mode, driver và loại đĩa.
- [ ] Đã theo dõi trạng thái copy/replication đến khi hoàn tất.
- [ ] Đã khởi chạy thử và smoke test tại từng nhóm account/region.
- [ ] Đã ghi image ID và trạng thái đích vào manifest.
- [ ] Đã có quy trình retry, idempotency và xử lý lỗi.
- [ ] Đã giữ phiên bản ổn định để rollback.
- [ ] Đã xác định thời hạn lưu giữ và điều kiện xóa image cũ.
- [ ] Đã kiểm tra DR mà không phụ thuộc account hoặc region nguồn.

## Kết luận

Phân phối image qua nhiều region và account giúp tổ chức triển khai máy ảo nhất quán, mở rộng dịch vụ và chuẩn bị khả năng khôi phục. Để quy trình đáng tin cậy, cần phân biệt chia sẻ với sao chép, quản lý đầy đủ snapshot và khóa mã hóa, kiểm soát quyền theo account, kiểm thử tại từng region đích và lưu manifest cho mỗi phiên bản. Khi kết hợp image factory tập trung, pipeline có thể lặp lại, phiên bản bất biến và quy trình rollback rõ ràng, tổ chức có thể đưa image đã kiểm thử đến đúng môi trường mà vẫn kiểm soát được bảo mật, chi phí và vòng đời.
