# Xây dựng image theo pipeline và quản lý phiên bản

Machine image là mẫu đã được chuẩn bị để khởi tạo máy ảo với hệ điều hành, cấu hình khởi động, phần mềm nền và các thành phần cần thiết. Khi nhiều máy ảo được tạo từ cùng một image đã kiểm thử, đội vận hành có thể triển khai môi trường nhất quán, rút ngắn thời gian khởi tạo và kiểm soát tốt hơn những gì được đưa vào máy.

Đối với **CLOUD_CORE_SERVICES_COMPUTE**, image là một phần của quy trình cung cấp năng lực tính toán: image cần tương thích với loại máy, kiến trúc CPU, hệ điều hành, agent nền tảng, yêu cầu bảo mật và cách ứng dụng được triển khai. Xây dựng image bằng pipeline giúp lặp lại quá trình này, tạo dấu vết kiểm toán và đưa phiên bản mới đến các môi trường theo cách có thể kiểm soát.

## 1. Machine image là gì?

Machine image là một artifact dùng để tạo máy ảo. Tùy nền tảng, image có thể chứa:

- Hệ điều hành và các gói hệ thống.
- Kernel, bootloader và cấu hình khởi động.
- Driver hoặc thành phần hỗ trợ thiết bị ảo.
- Cloud agent, guest agent hoặc công cụ quản lý của nhà cung cấp.
- Runtime, thư viện hệ thống và các gói phụ thuộc nền tảng.
- Cấu hình mặc định, script khởi tạo và chính sách bảo mật nền.
- Ứng dụng hoặc thành phần ứng dụng nếu tổ chức chọn cách đóng gói này.

Image thường được lưu dưới dạng artifact do nền tảng quản lý hoặc trong kho image riêng của tổ chức. Khi tạo máy ảo từ image, nhà cung cấp tạo ổ đĩa khởi động và thiết lập máy theo định dạng, cấu hình mà image hỗ trợ.

### 1.1. Phân biệt machine image và container image

Hai loại image có mục đích khác nhau:

| Tiêu chí | Machine image | Container image |
| --- | --- | --- |
| Đơn vị triển khai | Máy ảo hoặc máy tính toán hoàn chỉnh | Tiến trình/ứng dụng trong container |
| Hệ điều hành | Thường chứa hệ điều hành guest có thể khởi động | Thường chứa user space; dùng kernel của host |
| Thành phần chính | OS, boot, agent, driver, gói nền và có thể có ứng dụng | Ứng dụng, runtime, thư viện và filesystem cần thiết |
| Vòng đời | Thường thay đổi khi phát hành image hoặc thay máy ảo | Có thể phát hành độc lập với máy ảo host |
| Mục đích | Chuẩn hóa nền tảng máy tính toán | Chuẩn hóa môi trường chạy ứng dụng |

Một hệ thống có thể dùng cả hai: machine image cung cấp hệ điều hành và runtime container; container image cung cấp ứng dụng. Khi đó cần quản lý phiên bản và lỗ hổng ở cả hai lớp.

### 1.2. Image nền và golden image

**Base image** là image ban đầu do nhà cung cấp hoặc cộng đồng cung cấp, thường gồm hệ điều hành tối thiểu. **Golden image** là image chuẩn do tổ chức xây dựng và phê duyệt, chứa cấu hình nền, bản vá và công cụ được phép sử dụng.

Golden image giúp các nhóm dùng chung một nền tảng đã được kiểm tra. Tuy nhiên, nó chỉ có giá trị khi được cập nhật thường xuyên, có người chịu trách nhiệm, có nguồn gốc rõ ràng và được kiểm thử trước khi đưa vào sử dụng. Một image chuẩn cũ có thể trở thành nguồn rủi ro nếu tiếp tục chứa gói lỗi thời hoặc cấu hình không còn phù hợp.

## 2. Vì sao nên xây dựng image bằng pipeline?

Nếu mỗi máy ảo được cấu hình thủ công sau khi tạo, các máy có thể khác nhau theo thời gian: gói cài đặt không cùng phiên bản, một máy thiếu bản vá, máy khác có cấu hình riêng chưa được ghi lại. Những khác biệt này gây khó khăn khi điều tra lỗi, mở rộng số lượng máy và khôi phục sau sự cố.

Pipeline image giải quyết vấn đề bằng cách mô tả và tự động hóa các bước tạo artifact. Cùng một đầu vào và cùng phiên bản công cụ sẽ tạo ra image có nội dung được kiểm soát. Kết quả được kiểm thử, ghi metadata và phát hành như một phiên bản có thể tham chiếu.

Lợi ích chính:

- **Nhất quán:** máy mới được tạo từ cùng một phiên bản image có nền tảng tương đương.
- **Tái lập:** có thể truy lại mã nguồn, base image, gói cài đặt và cấu hình đã dùng.
- **Bảo mật:** bản vá, hardening và kiểm tra lỗ hổng trở thành bước bắt buộc trong quy trình.
- **Tốc độ triển khai:** giảm thao tác cấu hình thủ công sau khi khởi tạo máy.
- **Khả năng mở rộng:** autoscaling có thể tạo thêm máy từ image đã kiểm thử.
- **Khôi phục:** có thể tạo lại máy từ phiên bản đã phát hành hoặc quay về image trước đó khi cần.
- **Kiểm toán:** có lịch sử build, kết quả kiểm thử và người hoặc hệ thống phê duyệt.

Pipeline không loại bỏ việc cấu hình lúc khởi động. Những giá trị thay đổi theo môi trường như địa chỉ dịch vụ, vùng, tên cụm hoặc cấu hình ứng dụng vẫn cần được truyền qua cơ chế cấu hình runtime.

## 3. Thiết kế pipeline xây dựng image

Một pipeline thực tế thường có các giai đoạn sau:

~~~mermaid
flowchart TD
    A["Nguồn đầu vào<br/>Base image, mã cấu hình, phiên bản gói"] --> B["Build image trong môi trường cô lập"]
    B --> C["Cập nhật và hardening hệ điều hành"]
    C --> D["Kiểm thử khởi động và chức năng"]
    D --> E["Quét bảo mật và kiểm tra tuân thủ"]
    E --> F["Đóng gói metadata, SBOM và provenance"]
    F --> G["Phê duyệt và phát hành image bất biến"]
    G --> H["Phân phối đến vùng/môi trường"]
    H --> I["Rollout máy mới và theo dõi"]
    I --> J["Ngừng phiên bản cũ theo chính sách"]
~~~

### 3.1. Khai báo đầu vào có kiểm soát

Pipeline nên lấy đầu vào từ các nguồn có phiên bản:

- Base image được chọn rõ ràng bằng ID hoặc digest nếu nền tảng hỗ trợ.
- Mã cấu hình hệ điều hành và công cụ cài đặt được quản lý trong Git.
- Danh sách package hoặc repository có nguồn tin cậy.
- Phiên bản Packer, image builder, plugin và công cụ kiểm thử.
- Cấu hình build theo môi trường hoặc kiến trúc CPU.

Không nên tham chiếu một nhãn base image luôn trỏ đến bản mới nhất mà không lưu lại ID thực tế được sử dụng. Nhãn có thể thay đổi theo thời gian, khiến cùng một lần chạy pipeline nhưng tạo ra kết quả khác nhau.

### 3.2. Build trong môi trường tạm thời

Image builder thường tạo một máy ảo hoặc môi trường build tạm, cài đặt gói và áp dụng cấu hình, sau đó chụp thành image mới. Công cụ như Packer có thể mô tả các bước build bằng mã; một số nhà cung cấp cũng có dịch vụ image builder riêng.

Môi trường build cần được giới hạn quyền. Tài khoản build chỉ nên có quyền đọc base image, tạo tài nguyên tạm, ghi artifact vào kho image đích và ghi log cần thiết. Không cấp quyền quản trị toàn bộ tài khoản đám mây nếu pipeline chỉ cần tạo image trong một phạm vi cụ thể.

Build nên chạy trong môi trường cô lập, có mạng và repository được kiểm soát. Tài nguyên tạm cần được xóa sau khi build thành công hoặc thất bại để tránh phát sinh chi phí và để lại máy chưa được quản lý.

### 3.3. Cài đặt và cấu hình hệ điều hành

Các bước cấu hình thường bao gồm:

1. Cài bản vá hệ điều hành và cập nhật package theo chính sách.
2. Cài cloud/guest agent, driver và công cụ giám sát cần thiết.
3. Cài runtime hoặc dependency nền nếu tổ chức quản lý chúng ở lớp machine image.
4. Áp dụng cấu hình bảo mật như quyền file, dịch vụ được phép chạy, chính sách SSH/RDP và firewall host.
5. Thiết lập timezone, locale, logging và đồng bộ thời gian theo chuẩn tổ chức.
6. Xóa cache package, file tạm, lịch sử shell và dữ liệu build không cần thiết.
7. Chuẩn bị image cho lần khởi động đầu tiên, chẳng hạn để cloud-init hoặc agent thực hiện cấu hình theo instance.

Không nên ghi sẵn khóa riêng, mật khẩu, token, chứng thư cá nhân hoặc thông tin xác thực môi trường production vào image. Image có thể được sao chép, chia sẻ hoặc dùng để tạo nhiều máy; bí mật được bake vào image sẽ lan theo mọi bản sao. Hãy cấp bí mật lúc runtime qua secret manager hoặc cơ chế danh tính workload có quyền hạn phù hợp.

### 3.4. Kiểm thử image

Một image chỉ build thành công chưa có nghĩa là có thể dùng trong production. Cần kiểm tra cả khả năng khởi động và hành vi của máy sau khi tạo:

- Máy ảo khởi động được với loại máy và kiến trúc CPU dự kiến.
- Hệ điều hành nhận đúng filesystem, network interface và thiết bị cần thiết.
- Cloud/guest agent hoạt động và máy có thể nhận cấu hình metadata theo cơ chế của nền tảng.
- SSH hoặc RDP tuân theo chính sách; tài khoản mặc định và quyền truy cập được kiểm tra.
- Dịch vụ nền khởi động đúng; không có daemon hoặc cổng không cần thiết.
- Logging, monitoring, time synchronization và cơ chế cập nhật hoạt động.
- Ứng dụng mẫu hoặc agent quản lý có thể cài đặt và chạy.
- Máy được tạo từ image không chứa trạng thái của máy build như host key, machine ID hoặc credential cần được sinh riêng.

Nên kiểm thử trên từng hệ điều hành, kiến trúc CPU và loại instance mà image sẽ hỗ trợ. Một image cho x86-64 không mặc nhiên khởi động được trên Arm; image cho một dòng hệ điều hành cũng không đảm bảo tương thích với mọi driver hoặc loại máy.

## 4. Bảo mật trong quy trình tạo image

Image là điểm bắt đầu của mọi máy được tạo từ nó. Lỗi bảo mật trong image có thể được nhân bản trên hàng trăm hoặc hàng nghìn instance, vì vậy bảo mật phải được tích hợp vào pipeline.

### 4.1. Giảm bề mặt tấn công

- Chọn base image tối thiểu, có nguồn gốc và lịch cập nhật rõ ràng.
- Chỉ cài package, dịch vụ và port thực sự cần thiết.
- Gỡ package, tài khoản mẫu và công cụ quản trị không dùng.
- Áp dụng nguyên tắc quyền tối thiểu cho user, service account và file.
- Tắt đăng nhập từ xa bằng tài khoản hoặc phương thức không được phép.
- Cấu hình logging, đồng bộ thời gian và cơ chế thu thập sự kiện.
- Thiết lập firewall host và chính sách bảo vệ phù hợp với vai trò máy.

Hardening cần dựa trên baseline được tổ chức phê duyệt. Không nên áp dụng máy móc một cấu hình chung cho mọi loại workload nếu nó vô hiệu hóa dịch vụ mà agent hoặc ứng dụng cần. Các ngoại lệ phải được ghi nhận và có thời hạn xem xét.

### 4.2. Quét lỗ hổng và quản lý thành phần

Pipeline có thể quét package hệ điều hành, thư viện, kernel và công cụ được cài trong image. Kết quả cần được đánh giá theo mức độ nghiêm trọng, khả năng khai thác, mức độ phơi lộ và khả năng giảm thiểu.

**SBOM (Software Bill of Materials)** là danh mục thành phần phần mềm có trong artifact. SBOM giúp xác định image nào bị ảnh hưởng khi một thư viện hoặc package có lỗ hổng mới được công bố. Nên lưu SBOM cùng phiên bản image và có thể truy vấn nó trong quy trình ứng phó sự cố.

Không phải mọi cảnh báo quét đều có cùng mức rủi ro. Pipeline cần chính sách rõ về lỗ hổng nào chặn phát hành, lỗ hổng nào cần phê duyệt ngoại lệ và ai chịu trách nhiệm xử lý. Ngoại lệ nên có lý do, phạm vi, người phê duyệt và ngày hết hạn.

### 4.3. Ký và xác minh nguồn gốc image

Đối với hệ thống có yêu cầu bảo đảm chuỗi cung ứng phần mềm, tổ chức có thể ký artifact hoặc metadata phát hành và lưu provenance của build. Provenance ghi lại nguồn đầu vào, công cụ, quy trình và danh tính pipeline tạo artifact.

Trước khi triển khai, hệ thống có thể xác minh chữ ký, nguồn phát hành và chính sách tin cậy. Điều này giúp phát hiện image bị thay thế hoặc được tạo từ pipeline không được phép. Cách ký và xác minh cụ thể phụ thuộc kho artifact và nền tảng đám mây đang sử dụng.

### 4.4. Tránh rò rỉ bí mật trong log và image

Pipeline cần tránh đưa credential vào:

- Mã nguồn cấu hình hoặc file biến môi trường được lưu cùng repository.
- Lệnh build, command line hoặc output log.
- File cấu hình tạm, shell history và cache package.
- Snapshot, image metadata hoặc script khởi tạo.

Nếu một bí mật đã xuất hiện trong image hoặc log, cần xem nó là đã bị lộ: thu hồi hoặc xoay vòng bí mật, đánh giá phạm vi artifact bị ảnh hưởng và tạo image mới sau khi loại bỏ dữ liệu đó. Xóa file trong một lớp filesystem không đảm bảo dữ liệu đã biến mất khỏi mọi layer hoặc snapshot.

## 5. Ví dụ pipeline khai báo bằng YAML

Ví dụ dưới đây minh họa cấu trúc pipeline độc lập với nhà cung cấp. Tên job và lệnh là placeholder; cần thay bằng image builder, công cụ quét và API của nền tảng đang sử dụng.

~~~yaml
stages:
  - validate
  - build
  - test
  - security
  - publish

variables:
  IMAGE_FAMILY: "linux-app-base"
  IMAGE_VERSION: "2026.11.22-1"

validate-definition:
  stage: validate
  script:
    - validate-image-definition
    - verify-pinned-base-image
    - check-no-secrets-in-source

build-image:
  stage: build
  needs: ["validate-definition"]
  script:
    - image-builder build --definition image.pkr.hcl
    - record-build-metadata
  artifacts:
    paths:
      - build-metadata.json

test-image:
  stage: test
  needs: ["build-image"]
  script:
    - launch-test-instance
    - verify-boot-and-agents
    - run-os-and-service-tests
    - destroy-test-instance

scan-image:
  stage: security
  needs: ["test-image"]
  script:
    - scan-image-vulnerabilities
    - generate-sbom
    - verify-hardening-policy

publish-image:
  stage: publish
  needs: ["scan-image"]
  rules:
    - if: '$RELEASE_APPROVED == "true"'
  script:
    - sign-image-and-metadata
    - publish-immutable-image
    - record-image-id-and-digest
~~~

Trong pipeline thực tế, build metadata cần ghi lại ít nhất base image ID/digest, phiên bản hệ điều hành, phiên bản công cụ build, commit cấu hình, danh sách package, thời điểm build, kết quả kiểm thử, SBOM và ID image sau khi phát hành.

Pipeline cần dừng nếu kiểm tra đầu vào, build, boot test hoặc chính sách bảo mật thất bại. Chỉ bước publish mới có quyền ghi vào kho image dùng chung; môi trường test nên dùng artifact tạm hoặc kho cách ly.

## 6. Quản lý phiên bản image

Mỗi image phát hành cần có định danh duy nhất và có thể truy ngược. Không nên chỉ dựa vào tên dễ đọc như latest hoặc stable vì nhãn có thể được chuyển sang artifact khác.

### 6.1. Quy ước đặt phiên bản

Một quy ước có thể kết hợp tên họ image, hệ điều hành, kiến trúc, phiên bản nền và ngày build:

~~~text
linux-app-base-ubuntu24-arm64-2026.11.22-1
~~~

Các thành phần có thể biểu thị:

- Vai trò hoặc họ image: linux-app-base.
- Hệ điều hành và phiên bản: ubuntu24.
- Kiến trúc: arm64.
- Ngày phát hành: 2026.11.22.
- Số lần build trong ngày: 1.

Quy ước phải nhất quán và không được chứa bí mật hoặc dữ liệu nhạy cảm. Tên chỉ hỗ trợ con người đọc; hệ thống triển khai nên lưu ID bất biến hoặc digest mà nền tảng cấp.

### 6.2. Phân biệt version, ID và alias

| Định danh | Mục đích | Cách sử dụng |
| --- | --- | --- |
| Version | Phiên bản do tổ chức đặt | Theo dõi phát hành và trao đổi giữa các nhóm |
| Image ID | Định danh artifact trong nền tảng | Tham chiếu chính xác image khi tạo máy |
| Digest/checksum | Dấu kiểm tra nội dung nếu nền tảng hỗ trợ | Xác minh artifact không bị thay đổi |
| Alias/channel | Nhãn như stable, candidate hoặc production | Tìm phiên bản theo kênh phát hành |

Alias thuận tiện cho người dùng nhưng có thể thay đổi đích. Một triển khai cần có thể tái tạo nên ghi lại Image ID hoặc digest cụ thể cùng cấu hình triển khai.

### 6.3. Image bất biến

Sau khi phát hành, nội dung image nên được coi là bất biến. Nếu cần thay đổi package, bản vá hoặc cấu hình nền, hãy tạo một phiên bản mới. Việc sửa trực tiếp một image đang được tham chiếu khiến không thể biết chính xác máy mới sẽ được tạo từ nội dung nào.

Mô hình này hỗ trợ kiểm soát thay đổi: phiên bản cũ vẫn có thể được dùng để tái tạo môi trường trong thời gian lưu giữ, còn phiên bản mới đi qua đầy đủ pipeline và phê duyệt.

## 7. Phân phối và triển khai image

Sau khi phát hành, image có thể cần được sao chép đến các vùng, tài khoản hoặc môi trường khác nhau. Quy trình phân phối nên xác minh artifact đích khớp với nguồn, quyền chia sẻ đúng phạm vi và trạng thái replication đã hoàn tất trước khi triển khai.

Một quy trình rollout có kiểm soát thường gồm:

1. Triển khai image mới vào môi trường thử nghiệm hoặc một nhóm máy nhỏ.
2. Kiểm tra boot time, health check, log, kết nối mạng và hành vi ứng dụng.
3. Mở rộng sang một nhóm canary hoặc một phần lưu lượng.
4. Theo dõi lỗi khởi động, latency, CPU/RAM, agent và sự kiện hệ điều hành.
5. Mở rộng dần đến toàn bộ nhóm máy khi các tiêu chí đạt yêu cầu.
6. Dừng rollout và chuyển về phiên bản trước nếu xuất hiện lỗi vượt ngưỡng.

Với autoscaling group hoặc managed instance group, cần cập nhật template hoặc cấu hình launch để tham chiếu image ID mới. Máy hiện có có thể tiếp tục chạy image cũ cho đến khi được thay thế theo chiến lược rolling replacement hoặc lịch bảo trì.

Không nên xóa image cũ ngay sau khi phát hành bản mới. Giữ lại đủ phiên bản để phục vụ rollback, điều tra sự cố và đáp ứng yêu cầu kiểm toán.

## 8. Cập nhật và vá lỗi image

Hệ điều hành và package liên tục nhận bản vá bảo mật, sửa lỗi và cập nhật tương thích. Image vì vậy cần có lịch rebuild định kỳ và cơ chế xử lý bản vá khẩn cấp.

### 8.1. Rebuild thay vì sửa từng máy

Với mô hình image bất biến, khi có bản vá:

1. Cập nhật base image hoặc danh sách package được phép.
2. Chạy pipeline để build phiên bản image mới.
3. Quét lỗ hổng và kiểm tra cấu hình.
4. Kiểm thử khởi động, agent và ứng dụng.
5. Phê duyệt, phát hành và rollout.
6. Thay thế các máy đang chạy phiên bản cũ theo chính sách.

Việc vá trực tiếp một máy đang chạy đôi khi cần thiết để xử lý khẩn cấp, nhưng trạng thái đó phải được đưa trở lại mã cấu hình và pipeline. Nếu không, máy sẽ khác với image chuẩn và có thể mất thay đổi khi được thay thế.

### 8.2. Chính sách cập nhật

Tổ chức nên xác định:

- Chu kỳ rebuild định kỳ theo hệ điều hành và mức độ quan trọng.
- Thời hạn xử lý lỗ hổng theo mức độ nghiêm trọng và khả năng khai thác.
- Cách xử lý bản vá kernel cần reboot.
- Thời gian kiểm thử và phê duyệt trong trường hợp khẩn cấp.
- Cách thông báo và thay thế image sắp hết hỗ trợ.
- Cách xử lý ứng dụng cần phiên bản OS hoặc runtime cụ thể.

Không nên dùng một chu kỳ cứng cho mọi image nếu mức độ rủi ro khác nhau. Image chứa thành phần phơi ra Internet hoặc xử lý dữ liệu nhạy cảm có thể cần lịch cập nhật và kiểm tra nghiêm ngặt hơn.

## 9. Quản lý vòng đời và dọn dẹp phiên bản

Kho image có thể tích lũy nhiều phiên bản, bản build lỗi, image thử nghiệm và image không còn được sử dụng. Nếu không có chính sách vòng đời, việc tìm phiên bản đáng tin cậy trở nên khó khăn và chi phí lưu trữ tăng.

Một chính sách vòng đời nên có:

- **Trạng thái:** draft, candidate, approved, deprecated hoặc retired.
- **Chủ sở hữu:** nhóm chịu trách nhiệm cập nhật và xử lý lỗ hổng.
- **Ngày tạo và ngày hết hạn xem xét:** xác định tuổi artifact và lịch đánh giá.
- **Phạm vi sử dụng:** môi trường, tài khoản, vùng và kiến trúc được phép.
- **Phiên bản thay thế:** chỉ rõ image mới thay thế image nào.
- **Thời gian lưu giữ:** đủ để rollback và kiểm toán theo chính sách tổ chức.
- **Điều kiện xóa:** không còn workload tham chiếu, hết thời gian giữ và có phê duyệt cần thiết.

Trước khi xóa image, cần kiểm tra template khởi tạo máy, autoscaling group, pipeline, môi trường phục hồi và tài khoản khác có đang tham chiếu image đó hay không. Việc xóa image có thể làm hỏng khả năng tạo máy mới hoặc khôi phục môi trường, dù máy đang chạy từ image đó vẫn hoạt động.

## 10. Ví dụ: phát hành image Linux mới

Một nhóm vận hành có image chuẩn cho máy ảo chạy dịch vụ Java. Image hiện tại dùng hệ điều hành Linux, cloud agent, JDK và agent giám sát. Nhóm cần cập nhật bản vá bảo mật và nâng JDK theo lịch phát hành.

Nhóm thực hiện:

1. Chọn base image đã được phê duyệt và ghi lại ID cụ thể.
2. Cập nhật mã cấu hình cài đặt hệ điều hành, JDK và agent.
3. Chạy pipeline trong tài khoản build có quyền giới hạn.
4. Quét package, tạo SBOM và xác minh không có credential trong image.
5. Tạo máy thử nghiệm từ image mới, kiểm tra boot, SSH, logging, agent và ứng dụng mẫu.
6. Ghi version, Image ID, digest, commit cấu hình và kết quả kiểm thử.
7. Phát hành phiên bản mới vào kênh candidate, triển khai canary rồi mở rộng.
8. Theo dõi lỗi khởi động, thời gian sẵn sàng, p95/p99 và log hệ điều hành.
9. Chuyển alias production sang phiên bản đã phê duyệt, đồng thời giữ image trước đó trong thời gian rollback.

Nếu canary xuất hiện lỗi tương thích, nhóm dừng rollout và chuyển cấu hình tạo máy về Image ID trước đó. Bản image mới vẫn được giữ ở trạng thái candidate để điều tra; sau khi sửa, pipeline phải tạo và kiểm thử một artifact mới.

## 11. Các điểm cần chú ý với Windows và Linux

Quy trình chung có thể áp dụng cho cả hai hệ điều hành, nhưng bước chuẩn bị image có khác biệt.

| Nội dung | Linux | Windows |
| --- | --- | --- |
| Công cụ khởi tạo | cloud-init hoặc guest agent tùy nền tảng | Sysprep và guest agent/công cụ của nhà cung cấp tùy nền tảng |
| Định danh máy | Cần xử lý machine ID, host key và trạng thái khởi tạo | Cần xử lý SID, hostname và trạng thái specialize theo quy trình hỗ trợ |
| Cập nhật | Package manager và kernel update | Windows Update, servicing stack và cập nhật driver |
| Truy cập quản trị | SSH và sudo theo chính sách | RDP, tài khoản quản trị và chính sách domain |
| Kiểm thử | systemd/service, filesystem, network, agent | Boot, dịch vụ Windows, driver, activation và agent |

Không nên clone image Windows đã khởi tạo mà bỏ qua quy trình generalize/specialize phù hợp. Với Linux, cần bảo đảm các định danh duy nhất được tạo lại đúng lúc và không mang host key hoặc machine ID của máy build sang các máy mới.

Các yêu cầu về license, activation và quyền sử dụng hệ điều hành cũng cần được xác minh theo loại image và thỏa thuận với nhà cung cấp.

## 12. Các sai lầm thường gặp

- Cài đặt image thủ công trên một máy rồi chụp lại mà không lưu quy trình.
- Dùng base image hoặc package tag trôi nổi, không ghi ID đầu vào.
- Ghi credential, SSH private key hoặc token vào image.
- Chỉ kiểm tra build thành công mà không khởi động máy từ image.
- Không kiểm tra tương thích theo kiến trúc CPU hoặc loại instance.
- Cập nhật trực tiếp máy production nhưng không cập nhật mã cấu hình.
- Dùng alias mutable làm định danh duy nhất trong triển khai cần tái lập.
- Không lưu SBOM, metadata, kết quả quét và lịch sử build.
- Xóa image cũ trước khi xác minh không còn workload tham chiếu.
- Không có quy trình rollback hoặc không kiểm tra image trước khi rollout diện rộng.
- Không cập nhật image chuẩn trong thời gian dài, khiến bản vá bị dồn tích.

## 13. Quy trình vận hành đề xuất

1. **Quản lý mã cấu hình:** lưu định nghĩa image, script cài đặt và chính sách hardening trong hệ thống kiểm soát phiên bản.
2. **Pin đầu vào:** cố định base image, package, builder và plugin bằng phiên bản hoặc ID cụ thể.
3. **Build có kiểm soát:** chạy trong môi trường tạm, quyền tối thiểu và log có thể truy vết.
4. **Kiểm thử nhiều lớp:** xác minh boot, OS, agent, network, security và ứng dụng mẫu.
5. **Quản lý chuỗi cung ứng:** tạo SBOM, lưu provenance, ký và xác minh artifact nếu quy trình yêu cầu.
6. **Phát hành bất biến:** cấp version và Image ID duy nhất; không sửa nội dung image đã phát hành.
7. **Rollout theo giai đoạn:** canary, theo dõi health và mở rộng khi đạt tiêu chí.
8. **Duy trì và thu hồi:** rebuild khi có bản vá, đánh dấu deprecated và xóa phiên bản theo chính sách.
9. **Kiểm tra khả năng phục hồi:** định kỳ thử tạo máy từ image hiện hành và phiên bản rollback.

Xây dựng image bằng pipeline biến cấu hình máy ảo thành một artifact có thể kiểm thử, truy vết và phát hành. Khi kết hợp image bất biến với quản lý phiên bản, kiểm tra bảo mật và rollout có kiểm soát, đội kỹ thuật có thể cung cấp máy tính toán nhất quán, giảm sai lệch cấu hình và phục hồi nhanh hơn khi có thay đổi gây lỗi.
