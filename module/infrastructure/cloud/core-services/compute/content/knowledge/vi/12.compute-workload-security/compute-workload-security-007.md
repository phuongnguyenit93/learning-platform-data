# Measured boot, attestation và xác minh môi trường thực thi

Máy ảo có thể được tạo từ image đã phê duyệt nhưng vẫn khởi động bằng firmware, bootloader, kernel hoặc cấu hình khác với dự kiến. Trong môi trường nhiều tài khoản và region, đội vận hành cần bằng chứng để biết máy đang chạy trên nền tảng nào, chuỗi khởi động đã nạp những thành phần gì và workload có đáp ứng chính sách bảo mật trước khi nhận dữ liệu nhạy cảm hay không.

**Measured boot** ghi nhận phép đo mật mã của các thành phần trong quá trình khởi động. **Attestation** dùng bằng chứng đó để một bên khác đánh giá trạng thái của thiết bị hoặc workload theo chính sách đã định. Khi kết hợp với Secure Boot, TPM, hệ thống quản lý khóa và quy trình phát hành image, tổ chức có thể phát hiện sai lệch trong chuỗi khởi động và chỉ cấp quyền truy cập cho môi trường đáp ứng yêu cầu.

Bài học này giải thích nền tảng của measured boot, TPM PCR, event log, local và remote attestation, cách verifier ra quyết định, cách dùng kết quả để kiểm soát secret hoặc workload, cùng các giới hạn cần hiểu trước khi đưa vào production.

## 1. Vì sao cần xác minh môi trường thực thi?

Một máy ảo có thể báo trạng thái running dù hệ điều hành đã khởi động với cấu hình không mong muốn. Ví dụ:

- Firmware hoặc bootloader đã bị thay đổi.
- Máy dùng image khác phiên bản được phê duyệt.
- Secure Boot bị tắt hoặc cấu hình khóa khởi động thay đổi.
- Kernel, initramfs hoặc tham số dòng lệnh kernel không đúng baseline.
- Một thành phần boot cũ có lỗ hổng vẫn được sử dụng.
- VM được tạo ở project/account hoặc host không đáp ứng yêu cầu.
- Workload chạy trong confidential VM nhưng không xác minh được bằng chứng của môi trường bảo mật.
- Secret được cấp cho instance chỉ dựa trên tag hoặc metadata do người triển khai kiểm soát.

Inventory, image ID và trạng thái của cloud control plane là thông tin quan trọng nhưng chưa đủ để chứng minh trạng thái boot thực tế. Measured boot bổ sung bằng chứng được tạo tại máy và gắn với phần cứng bảo mật hoặc cơ chế attestation của nền tảng.

### Các câu hỏi cần trả lời

Một quy trình xác minh môi trường thường cần biết:

1. Nền tảng có root of trust phù hợp không?
2. Chuỗi boot đã đo những thành phần nào?
3. Giá trị đo có khớp với phiên bản được phê duyệt không?
4. Bằng chứng có mới và thuộc đúng máy đang được kiểm tra không?
5. Có thành phần nào bị bỏ qua hoặc không được đo không?
6. Môi trường có đáp ứng chính sách trước khi nhận secret hoặc traffic không?
7. Khi hệ điều hành hoặc image được cập nhật, baseline được thay đổi và phê duyệt ra sao?

Attestation không thay thế toàn bộ bảo mật hệ thống. Nó cung cấp một tín hiệu có thể kiểm chứng để kết hợp với danh tính máy, chính sách mạng, quản lý lỗ hổng, giám sát runtime và kiểm soát truy cập.

## 2. Root of trust và chuỗi khởi động

### Root of trust là gì?

Root of trust là thành phần hoặc cơ chế tối thiểu mà hệ thống dựa vào để xác minh các bước tiếp theo. Trong boot chain, firmware hoặc phần cứng bảo mật có thể cung cấp điểm bắt đầu cho việc xác minh chữ ký và đo lường.

Một chuỗi khởi động thường có dạng:

1. CPU và firmware bắt đầu thực thi.
2. Firmware khởi tạo phần cứng và kiểm tra hoặc đo các thành phần tiếp theo.
3. Boot manager/bootloader được xác minh hoặc đo.
4. Bootloader nạp kernel và initramfs.
5. Kernel khởi tạo driver, module và hệ thống gốc.
6. Init system khởi chạy dịch vụ hệ điều hành.
7. Agent bảo mật, workload và ứng dụng được khởi động.

Chuỗi thực tế phụ thuộc kiến trúc BIOS/UEFI, hệ điều hành, hypervisor và nền tảng cloud. Không phải mọi thành phần đều được đo theo cùng cách trên mọi máy.

### Chain of trust

Chain of trust là mô hình trong đó mỗi giai đoạn xác minh hoặc đo thành phần kế tiếp trước khi chuyển quyền điều khiển. Nếu một thành phần không được xác minh đúng, hệ thống có thể từ chối boot, chuyển sang recovery hoặc ghi nhận trạng thái không đạt.

Cần phân biệt hai hành động:

- **Verify:** kiểm tra chữ ký hoặc tính toàn vẹn trước khi cho phép thực thi.
- **Measure:** tính giá trị mật mã của thành phần và ghi nhận vào vùng đo được bảo vệ.

Một thành phần có chữ ký hợp lệ vẫn có thể chứa lỗ hổng. Chữ ký chứng minh nguồn phát hành và tính toàn vẹn theo khóa tin cậy, nhưng không chứng minh phần mềm hoàn toàn an toàn. Việc đo giúp verifier biết chính xác phiên bản hoặc trạng thái đã được nạp để so với chính sách.

### Firmware và cấu hình boot

Firmware có thể quyết định boot mode, Secure Boot, danh sách khóa tin cậy, thiết bị boot và thứ tự boot. Những thay đổi này có thể ảnh hưởng đến kết quả đo.

Trong môi trường VM, một số trạng thái firmware được ảo hóa. Hypervisor và nhà cung cấp cloud quyết định cách firmware, vTPM và các phép đo được trình bày cho guest. Không nên giả định một VM có cùng mức bảo đảm với máy vật lý chỉ vì hệ điều hành hiển thị có TPM.

## 3. Secure Boot khác measured boot như thế nào?

Secure Boot và measured boot có liên quan nhưng giải quyết các câu hỏi khác nhau.

| Cơ chế | Mục tiêu | Hành động | Kết quả |
|---|---|---|---|
| Secure Boot | Ngăn thành phần boot không được tin cậy chạy | Kiểm tra chữ ký theo khóa và policy tin cậy | Cho phép hoặc từ chối thành phần boot |
| Measured boot | Ghi lại trạng thái các thành phần đã được nạp | Tính hash và mở rộng giá trị vào PCR | Có bằng chứng về chuỗi boot đã đo |
| Attestation | Đánh giá bằng chứng theo chính sách | Thu thập quote, event log và claims rồi xác minh | Kết luận môi trường đạt, không đạt hoặc chưa đủ bằng chứng |

### Secure Boot

UEFI Secure Boot sử dụng cơ sở dữ liệu khóa và chữ ký để kiểm tra bootloader hoặc thành phần boot theo policy. Nếu chữ ký không được tin cậy hoặc bị thu hồi, firmware có thể ngăn thành phần đó được thực thi.

Secure Boot giảm nguy cơ bootkit và thành phần boot không được phê duyệt. Tuy nhiên, một bootloader được ký hợp lệ nhưng có lỗ hổng vẫn có thể được chấp nhận nếu khóa và danh sách thu hồi chưa phản ánh rủi ro đó.

### Measured boot

Measured boot ghi nhận các phép đo của firmware, boot manager và những thành phần được cấu hình đo. Nó không nhất thiết ngăn một thành phần chạy. Thay vào đó, kết quả đo có thể được gửi tới verifier để so với baseline.

Nếu một bootloader lạ vẫn được thực thi nhưng được đo, PCR có thể khác giá trị mong đợi. Verifier có thể từ chối cấp secret hoặc đánh dấu máy cần điều tra.

### Kết hợp hai cơ chế

Một thiết kế thường dùng là bật Secure Boot để ngăn thành phần không được ký theo policy, đồng thời bật measured boot để ghi lại trạng thái chuỗi khởi động. Remote attestation sau đó xác minh các phép đo và các claims khác trước khi cấp quyền.

Không nên xem một cờ Secure Boot đang bật là bằng chứng duy nhất. Cần xác minh khóa, trạng thái thu hồi, firmware mode, phép đo và policy áp dụng.

## 4. TPM và Platform Configuration Register

### TPM là gì?

Trusted Platform Module (TPM) là thành phần bảo mật cung cấp các chức năng như tạo và bảo vệ khóa, thực hiện phép đo, lưu trạng thái bảo mật và tạo bằng chứng mật mã. TPM 2.0 là phiên bản phổ biến trong các nền tảng hiện đại.

TPM có thể là chip vật lý trên máy chủ hoặc TPM ảo (vTPM) do hypervisor cung cấp cho VM. Cách triển khai, mức bảo vệ khóa và trust boundary của vTPM phụ thuộc nền tảng.

### PCR lưu gì?

Platform Configuration Register (PCR) là thanh ghi lưu trạng thái đo. Một PCR không đơn giản chứa hash cuối cùng của một file. Khi có phép đo mới, giá trị PCR được mở rộng theo công thức:

\[
PCR_{new} = H(PCR_{old} \parallel measurement)
\]

Trong đó H là hàm băm được chọn và ký hiệu \(\parallel\) biểu diễn nối dữ liệu. Vì giá trị mới phụ thuộc giá trị cũ và phép đo mới, thứ tự các phép đo ảnh hưởng đến kết quả cuối.

PCR thường được nhóm theo mục đích và profile nền tảng. Một số hệ thống dùng các PCR riêng cho firmware, boot manager, Secure Boot policy hoặc cấu hình khác. Tuy nhiên, cách gán PCR không giống nhau trên mọi firmware và nền tảng. Verifier phải hiểu profile cụ thể thay vì hard-code giả định chung cho tất cả máy.

### Vì sao PCR hữu ích?

PCR nằm trong ranh giới bảo vệ của TPM. Phần mềm thông thường không thể tùy ý ghi một giá trị bất kỳ vào PCR như ghi file trên đĩa. Các thao tác extend tuân theo quy tắc TPM, giúp kết quả đo khó bị sửa giả mạo từ guest OS.

PCR có thể được dùng để:

- So sánh trạng thái boot với baseline.
- Ràng buộc việc sử dụng khóa vào một trạng thái PCR nhất định.
- Tạo quote được TPM ký để chứng minh trạng thái đo tại thời điểm yêu cầu.
- Phát hiện thay đổi firmware, bootloader hoặc policy boot đã được đo.

PCR không chứa mô tả dễ đọc về mọi thành phần. Để biết phép đo tương ứng với sự kiện nào, verifier thường cần event log.

## 5. Event log và cách diễn giải phép đo

### Event log là gì?

Trong quá trình boot, thành phần đo có thể ghi lại sự kiện như tên module, loại sự kiện, digest của thành phần và PCR được extend. Các sự kiện được lưu thành event log để bên xác minh có thể diễn giải.

Event log có thể chứa:

- Thành phần firmware được nạp.
- Boot manager hoặc bootloader.
- Kernel, initramfs hoặc driver.
- Cấu hình Secure Boot và các khóa liên quan.
- Thành phần được đo bởi cơ chế mở rộng như Linux IMA, nếu được bật.

Nội dung và định dạng log phụ thuộc nền tảng. Không phải mọi event đều là file hash; một số sự kiện mô tả cấu hình hoặc dữ liệu liên quan đến boot.

### Replay event log

Verifier có thể đọc event log, bắt đầu từ giá trị PCR khởi tạo theo chuẩn và lần lượt áp dụng phép extend cho từng digest. Giá trị tái tạo phải khớp với PCR được cung cấp trong TPM quote.

Quy trình này giúp phát hiện event log bị sửa hoặc không tương thích với trạng thái TPM. Nếu log không tái tạo được PCR, bằng chứng không hợp lệ hoặc chưa đầy đủ.

### Giá trị đo và reference values

Reference values là các giá trị kỳ vọng do tổ chức hoặc nhà cung cấp tin cậy công bố cho một cấu hình cụ thể. Chúng có thể được lập theo:

- Model máy hoặc loại VM.
- Phiên bản firmware.
- Boot mode và Secure Boot policy.
- Phiên bản bootloader, kernel và initramfs.
- Image release và cấu hình hệ điều hành.
- Phiên bản agent hoặc module được phép đo.

Một baseline quá rộng có thể chấp nhận cấu hình không mong muốn. Baseline quá hẹp có thể khiến mọi bản cập nhật hợp lệ đều bị từ chối. Cần quản lý reference values theo phiên bản, có nguồn gốc, người phê duyệt và thời gian hiệu lực.

### Event log không phải bằng chứng độc lập

Event log thường được thu từ hệ điều hành hoặc firmware và có thể bị sửa sau khi tạo. Vì vậy, cần đối chiếu log với PCR quote được TPM ký. Không tin event log chỉ vì nó đến từ máy cần xác minh.

## 6. Quote và local attestation

### TPM quote

TPM quote là cấu trúc bằng chứng trong đó TPM ký một tập PCR được chọn cùng thông tin liên quan. Quote thường được tạo bằng Attestation Key (AK) hoặc khóa attestation tương ứng.

Một quote có thể bao gồm:

- Digest của các PCR được yêu cầu.
- Thông tin về thuật toán hash.
- Giá trị nonce hoặc qualifying data do verifier gửi.
- Dấu thời gian hoặc bộ đếm liên quan theo cơ chế TPM.
- Chữ ký của khóa attestation.

Verifier kiểm tra chữ ký, xác minh khóa attestation và so sánh nonce để bảo đảm quote được tạo cho yêu cầu hiện tại.

### Nonce chống replay

Nếu không có nonce hoặc cơ chế freshness tương đương, kẻ tấn công có thể gửi lại một quote cũ từng hợp lệ. Verifier tạo một nonce ngẫu nhiên cho mỗi phiên attestation, gửi cho thiết bị và yêu cầu quote chứa nonce đó.

Khi nhận quote, verifier xác minh nonce khớp với giá trị vừa phát hành và chưa được sử dụng. Như vậy, bằng chứng cũ không thể được phát lại để vượt qua kiểm tra mới.

Nonce phải đủ ngẫu nhiên, có thời hạn ngắn và được gắn với phiên xác minh cụ thể.

### Local attestation

Local attestation là việc đánh giá trạng thái ngay trên thiết bị hoặc trong cùng một miền tin cậy. Ví dụ, TPM có thể cho phép unseal một khóa chỉ khi PCR đáp ứng policy đã cấu hình.

Một số ứng dụng có thể dùng TPM policy để ràng buộc thao tác ký hoặc giải mã với trạng thái boot. Nếu trạng thái đo thay đổi, TPM không giải phóng khóa.

Local attestation hữu ích cho bảo vệ khóa trên cùng máy, nhưng không thay thế remote attestation khi một dịch vụ bên ngoài cần xác minh VM trước khi cấp dữ liệu.

## 7. Remote attestation và vai trò của verifier

Remote attestation cho phép một bên độc lập đánh giá trạng thái của máy từ xa. Ví dụ, một secret manager hoặc dịch vụ cấp workload identity muốn xác minh VM trước khi cung cấp credential.

### Các thành phần chính

- **Attester:** máy hoặc workload tạo bằng chứng.
- **Evidence:** quote, event log, chứng thư, claims và dữ liệu liên quan.
- **Verifier:** hệ thống kiểm tra chữ ký, freshness, reference values và policy.
- **Relying party:** dịch vụ dựa vào kết quả để quyết định cấp quyền hoặc từ chối.
- **Reference values:** baseline được phê duyệt để so sánh.
- **Attestation policy:** quy tắc xác định trạng thái nào được chấp nhận.

Verifier có thể là một dịch vụ riêng, một phần của secret manager, hệ thống identity hoặc dịch vụ attestation của nhà cung cấp.

### Luồng remote attestation

~~~mermaid
sequenceDiagram
    participant V as Verifier
    participant A as Attester VM
    participant T as TPM hoặc nền tảng
    participant R as Relying Party

    V->>A: Gửi challenge nonce
    A->>T: Yêu cầu quote PCR với nonce
    T-->>A: Quote có chữ ký
    A-->>V: Quote, event log và claims
    V->>V: Xác minh chứng thư, chữ ký và nonce
    V->>V: Replay log và so reference values
    V->>R: Kết quả attestation có thời hạn
    R->>A: Cấp hoặc từ chối quyền truy cập
~~~

### Các bước verifier phải thực hiện

1. Xác định attester và loại bằng chứng được chấp nhận.
2. Xác minh chuỗi chứng thư hoặc danh tính khóa attestation.
3. Kiểm tra quote có chữ ký hợp lệ.
4. Kiểm tra nonce và freshness.
5. Xác nhận các PCR được quote đúng với policy.
6. Replay event log và so digest với PCR.
7. So reference values với baseline được phê duyệt.
8. Đánh giá trạng thái thu hồi, phiên bản firmware và policy.
9. Kiểm tra các claims bổ sung như instance identity, region hoặc workload measurement.
10. Trả kết quả có thời hạn, phạm vi và lý do đạt/không đạt.

Kết quả nên phân biệt ít nhất ba trạng thái:

- **Pass:** bằng chứng hợp lệ và đáp ứng toàn bộ policy.
- **Fail:** bằng chứng hợp lệ nhưng trạng thái không đáp ứng policy.
- **Indeterminate:** thiếu bằng chứng, không xác minh được chữ ký, event log lỗi hoặc dịch vụ xác minh không đủ dữ liệu.

Không nên biến lỗi verifier hoặc timeout thành trạng thái pass. Với dữ liệu nhạy cảm, chính sách thường phải fail closed hoặc giới hạn quyền khi trạng thái indeterminate.

## 8. Xác minh image, boot state và runtime là ba lớp khác nhau

Measured boot thường tập trung vào chuỗi khởi động. Để đánh giá môi trường đầy đủ, cần phân biệt ba lớp:

| Lớp | Bằng chứng tiêu biểu | Câu hỏi được trả lời | Giới hạn |
|---|---|---|---|
| Image/provenance | Image ID, chữ ký artifact, build manifest, SBOM | Image có đến từ pipeline tin cậy và đã được duyệt không? | Không chứng minh image đó thực sự đã boot hoặc không bị thay đổi sau khi tạo |
| Boot state | TPM PCR, quote và event log | Thành phần boot đã đo có khớp baseline không? | Không tự chứng minh mọi tiến trình sau boot đều an toàn |
| Runtime/workload | IMA measurement, EDR, workload identity, process policy, TEE report | Workload hoặc môi trường đang chạy có đáp ứng policy bổ sung không? | Phạm vi phụ thuộc cơ chế đo, coverage và trust boundary |

Một image có chữ ký hợp lệ vẫn có thể boot với firmware hoặc kernel khác nếu cấu hình cho phép. Một boot state đạt cũng không chứng minh ứng dụng không có lỗ hổng hoặc không bị khai thác sau boot.

Vì vậy, quy trình nên kết hợp image provenance, measured boot, runtime monitoring và policy của workload.

### Runtime measurement với Linux IMA

Linux Integrity Measurement Architecture (IMA) có thể đo hoặc appraisal file được truy cập/thực thi theo policy. Digest có thể được mở rộng vào PCR và ghi vào measurement list.

IMA có thể giúp theo dõi thay đổi file sau boot, nhưng coverage phụ thuộc policy và kernel configuration. Nếu policy chỉ đo một số đường dẫn, file ngoài phạm vi đó không được chứng minh. Cần quản lý policy, event log và reference values riêng.

Không nên tuyên bố measured boot chứng minh toàn bộ trạng thái runtime nếu chỉ thu PCR boot truyền thống.

## 9. Attestation cho confidential VM và trusted execution environment

### Confidential computing là gì?

Confidential computing dùng cơ chế phần cứng để bảo vệ dữ liệu đang được xử lý, thường bằng mã hóa bộ nhớ và kiểm soát truy cập giữa guest với host hoặc hypervisor. Mục tiêu là giảm khả năng host hoặc phần mềm đặc quyền đọc nội dung bộ nhớ workload.

Các công nghệ có thể gặp:

- AMD SEV-SNP cho confidential VM trên nền tảng hỗ trợ.
- Intel TDX cho confidential VM trên nền tảng hỗ trợ.
- Arm Confidential Compute Architecture (CCA) trong các triển khai tương thích.
- Trusted Execution Environment (TEE) cho một vùng thực thi cô lập trong một hệ thống.

Các cơ chế này có threat model, bằng chứng và giới hạn khác nhau. Không thể coi mọi VM có mã hóa đĩa hoặc vTPM là confidential VM.

### Attestation report của TEE

Confidential VM có thể tạo attestation report chứa measurement của firmware, boot chain hoặc trạng thái bảo vệ của guest, cùng claims về nền tảng. Report có thể được ký bởi phần cứng hoặc dịch vụ bảo mật của nhà cung cấp.

Verifier kiểm tra:

- Chữ ký và chuỗi chứng thư gốc.
- Measurement của guest hoặc firmware.
- Phiên bản TCB (Trusted Computing Base).
- Trạng thái cập nhật bảo mật và thu hồi.
- Policy về debug, migration hoặc thuộc tính bảo vệ.
- Nonce hoặc dữ liệu challenge gắn với phiên xác minh.
- Claims về workload nếu được hỗ trợ.

Một report hợp lệ chỉ cho biết bằng chứng phù hợp với trust model và policy đã chọn. Nó không bảo đảm ứng dụng không có lỗi logic, secret không bị lộ qua log hoặc dữ liệu không bị gửi ra ngoài.

### Phân biệt vTPM và confidential VM

vTPM cung cấp giao diện TPM ảo cho guest. Nó có thể lưu PCR và tạo quote trong mô hình do hypervisor quản lý. Mức bảo vệ phụ thuộc cách nhà cung cấp lưu khóa, cô lập vTPM và xác minh host.

Confidential VM sử dụng cơ chế phần cứng để bảo vệ bộ nhớ guest và có thể tạo bằng chứng attestation riêng cho trạng thái confidential computing. Một confidential VM có thể có vTPM, nhưng hai khái niệm không đồng nghĩa.

## 10. Dùng attestation để kiểm soát cấp secret và quyền truy cập

Một ứng dụng thực tế là chỉ cấp secret hoặc token khi VM chứng minh được trạng thái boot đáp ứng policy.

### Luồng cấp secret có điều kiện

1. VM khởi động và tạo quote.
2. VM gửi evidence tới attestation verifier.
3. Verifier xác minh quote, event log và reference values.
4. Verifier trả một kết quả có chữ ký hoặc token ngắn hạn.
5. Secret manager xác minh kết quả và danh tính workload.
6. Secret manager chỉ cấp secret phù hợp với role và environment.
7. Token hết hạn nhanh; workload phải xác minh lại theo chu kỳ hoặc khi có thay đổi quan trọng.

Kết quả attestation cần gắn với danh tính VM hoặc workload cụ thể, không chỉ trả một boolean chung. Nếu chỉ có “attestation passed” mà không xác định máy, thời điểm và policy version, relying party khó giới hạn quyền.

### Ràng buộc audience và thời hạn

Token attestation nên có:

- Subject: máy hoặc workload được xác minh.
- Audience: dịch vụ duy nhất được phép sử dụng token.
- Issued-at và expiry ngắn.
- Policy ID/version.
- Measurement hoặc trạng thái đã được đánh giá.
- Nonce/session ID hoặc liên kết tới phiên xác minh.
- Chữ ký của verifier.

Relying party cần kiểm tra audience, thời hạn, chữ ký và danh tính subject. Không dùng token cho một dịch vụ ở dịch vụ khác nếu không được policy cho phép.

### Tránh cấp secret dài hạn

Ngay cả khi attestation pass, nên ưu tiên credential ngắn hạn và quyền tối thiểu. Nếu VM bị xâm nhập sau khi boot, secret dài hạn có thể tiếp tục bị sử dụng. Cần có rotation, revoke, audit và cơ chế đánh giá lại.

### Xử lý khi attestation thất bại

Nếu verifier trả fail hoặc indeterminate:

- Không cấp secret nhạy cảm.
- Giữ VM ngoài load balancer nếu policy yêu cầu.
- Ghi lý do và evidence ID vào audit log.
- Cho phép quy trình recovery hoặc reimage có kiểm soát.
- Không tự động hạ policy để máy tiếp tục hoạt động.

Đối với hệ thống cần tính sẵn sàng, có thể dùng degraded mode chỉ cho phép tác vụ không nhạy cảm, nhưng phải được định nghĩa rõ trong policy.

## 11. Quản lý reference values và cập nhật hệ thống

### Baseline phải có nguồn gốc

Reference values cần được tạo từ image và firmware đã qua kiểm thử, không lấy từ một máy bất kỳ chỉ vì máy đó đang chạy ổn định.

Một quy trình chuẩn:

1. Build image từ nguồn đã phê duyệt.
2. Cập nhật firmware, bootloader và hệ điều hành.
3. Khởi chạy trên cấu hình phần cứng mục tiêu.
4. Thu event log và PCR qua attestation.
5. Xác minh chuỗi boot và phần mềm dự kiến.
6. Phê duyệt baseline cùng phiên bản image/firmware.
7. Lưu manifest, chữ ký và thời hạn hiệu lực.
8. Phân phối baseline tới verifier.

Baseline nên gắn với loại máy, firmware profile, kiến trúc và cấu hình boot. Không so sánh PCR của hai nền tảng khác nhau chỉ vì chúng chạy cùng phiên bản Linux.

### Firmware và kernel update có thể thay đổi PCR

Một bản cập nhật firmware, bootloader, kernel, initramfs hoặc Secure Boot database có thể làm PCR thay đổi. Đây không nhất thiết là dấu hiệu tấn công. Verifier cần biết phiên bản mới có hợp lệ hay không.

Có thể quản lý nhiều baseline đồng thời trong giai đoạn rollout:

- Baseline hiện tại được phép.
- Baseline mới đang canary.
- Baseline cũ được giữ trong thời gian rollback ngắn.
- Baseline bị thu hồi khi có lỗ hổng nghiêm trọng.

Không giữ baseline cũ vô thời hạn. Một policy cho phép mọi phiên bản trước đó có thể vô tình chấp nhận bootloader hoặc firmware đã bị thu hồi.

### Phê duyệt thay đổi

Thay đổi reference values nên có review, chữ ký và audit. Cần ghi rõ lý do, image/firmware version, phạm vi áp dụng, người phê duyệt và thời điểm hết hiệu lực.

Không tự động thêm mọi phép đo mới quan sát được vào allowlist. Nếu một máy bị xâm nhập, tự động học giá trị đo từ nó có thể biến trạng thái độc hại thành baseline tin cậy.

## 12. Triển khai attestation trong môi trường nhiều VM

### Phân nhóm policy

Một tổ chức có thể có nhiều nhóm workload:

- Development: dữ liệu thử nghiệm, policy có thể linh hoạt hơn nhưng vẫn cần xác minh nguồn image.
- Staging: gần production, dùng baseline gần tương đương.
- Production: policy nghiêm ngặt, chỉ chấp nhận image và firmware đã duyệt.
- Workload nhạy cảm: yêu cầu confidential VM, TEE hoặc attestation nâng cao.
- Disaster recovery: baseline và key policy phải hoạt động ở region dự phòng.

Mỗi nhóm cần policy rõ ràng, không dùng một allowlist quá rộng cho toàn bộ tổ chức.

### Tích hợp với orchestration

Trong hệ thống VM tự quản lý, provisioning workflow có thể đợi attestation trước khi đăng ký máy vào load balancer hoặc cấp credential.

Trong Kubernetes hoặc môi trường container, attestation có thể áp dụng cho node, confidential workload hoặc agent bảo mật tùy nền tảng. Cần phân biệt attestation của node với xác minh image/container. Một node được attestation không tự chứng minh mọi container trên node đều đáng tin cậy.

### Xác minh theo chu kỳ

Boot attestation thường diễn ra lúc khởi động. Nếu policy yêu cầu, có thể xác minh lại định kỳ hoặc trước thao tác nhạy cảm. Tuy nhiên, quote PCR boot không tự cập nhật để phản ánh mọi thay đổi runtime. Đối với runtime integrity, cần cơ chế đo riêng như IMA, EDR hoặc attestation của TEE có hỗ trợ trạng thái workload.

### Mở rộng verifier

Verifier cần có khả năng:

- Xử lý lượng quote lớn mà không trở thành bottleneck.
- Cache reference values có chữ ký và phiên bản.
- Ghi audit log mà không lưu dữ liệu nhạy cảm không cần thiết.
- Theo dõi chứng thư hết hạn, thu hồi và TCB status.
- Có HA và kế hoạch phục hồi.
- Từ chối request quá hạn hoặc nonce đã dùng.
- Cập nhật policy có kiểm soát.

Nếu verifier không khả dụng, relying party phải có hành vi được định nghĩa trước. Không nên tự động cấp quyền nhạy cảm khi không thể xác minh.

## 13. Quan sát, audit và xử lý sự cố

### Các metric nên theo dõi

- Tỷ lệ attestation pass, fail và indeterminate.
- Thời gian từ challenge đến kết quả.
- Số lượng quote không hợp lệ hoặc nonce bị replay.
- Số máy có PCR không khớp baseline.
- Số reference values sắp hết hiệu lực.
- Chứng thư attestation sắp hết hạn hoặc bị thu hồi.
- Tỷ lệ VM chưa hoàn tất boot measurement.
- Lỗi truy cập secret do attestation policy.
- Tình trạng verifier và dịch vụ cung cấp reference values.

### Audit record

Mỗi lần xác minh nên ghi nhận:

- Attester/workload ID.
- Thời gian và challenge/session ID.
- Policy ID và policy version.
- Reference value set được sử dụng.
- Trạng thái pass/fail/indeterminate.
- Lý do từ chối hoặc claim không đạt.
- Evidence digest hoặc ID để truy xuất có kiểm soát.
- Quyết định của relying party, ví dụ cấp secret hay từ chối.

Không ghi private key, secret, token đầy đủ hoặc dữ liệu workload nhạy cảm vào audit log.

### Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| TPM không được nhận diện | vTPM chưa bật, driver hoặc firmware thiếu | Kiểm tra cấu hình VM, thiết bị TPM và driver guest |
| Quote không xác minh được | Sai AK certificate, chữ ký hoặc thuật toán | Kiểm tra trust chain, key enrollment và thuật toán PCR |
| Nonce không khớp | Quote cũ, session nhầm hoặc lỗi triển khai challenge | Kiểm tra nonce, session binding và thời hạn |
| Event log không replay khớp PCR | Log thiếu, sai thứ tự, định dạng không hỗ trợ hoặc bị sửa | Thu lại log, kiểm tra profile và thuật toán hash |
| PCR khác baseline sau update | Firmware, bootloader, kernel hoặc Secure Boot policy đã đổi | So sánh event log và release manifest; xác minh bản cập nhật |
| Secure Boot bật nhưng attestation fail | Khóa, PCR, TCB hoặc policy khác baseline | Kiểm tra toàn bộ claims, không chỉ trạng thái Secure Boot |
| Attestation pass nhưng app bị xâm nhập | Chỉ đo boot, không có runtime integrity | Bổ sung IMA/EDR, workload controls và giám sát |
| Secret manager từ chối token | Audience, subject, policy version hoặc expiry không đúng | Kiểm tra token claims và mapping danh tính |
| Confidential VM report không hợp lệ | Chứng thư, TCB status hoặc report format không được hỗ trợ | Cập nhật verifier và reference data từ nguồn tin cậy |

### Quy trình điều tra

1. Xác định máy và phiên bản image/firmware đang được kiểm tra.
2. Kiểm tra TPM/vTPM hoặc thiết bị attestation có sẵn.
3. Thu quote mới với nonce mới.
4. Xác minh chứng thư và chữ ký.
5. Kiểm tra event log và replay PCR.
6. So sánh từng sự kiện khác biệt với manifest phát hành.
7. Xác định thay đổi có được phê duyệt hay không.
8. Kiểm tra TCB status và trạng thái thu hồi nếu là confidential computing.
9. Quyết định giữ máy cách ly, cập nhật baseline hay reimage.
10. Lưu audit record và cập nhật quy trình nếu phát hiện lỗ hổng.

Không thêm phép đo chưa rõ nguồn gốc vào allowlist chỉ để làm pipeline xanh trở lại.

## 14. Giới hạn và các hiểu nhầm thường gặp

1. **Secure Boot đồng nghĩa measured boot.** Secure Boot xác minh chữ ký; measured boot ghi lại phép đo. Có thể bật một cơ chế mà thiếu cơ chế còn lại.
2. **TPM có nghĩa máy an toàn tuyệt đối.** TPM cung cấp primitive và ranh giới bảo vệ; chất lượng thiết kế phụ thuộc firmware, provisioning, policy và verifier.
3. **PCR là danh sách hash file.** PCR là trạng thái mở rộng theo thứ tự; event log mới cung cấp ngữ cảnh sự kiện.
4. **Event log có thể tự chứng minh tính toàn vẹn.** Log cần được đối chiếu với quote có chữ ký.
5. **Quote hợp lệ nghĩa boot state tốt.** Quote hợp lệ chỉ chứng minh TPM ký các PCR đã chọn; verifier vẫn phải kiểm tra nonce, reference values và policy.
6. **Measured boot chứng minh runtime không bị sửa.** Boot measurement không tự theo dõi mọi thay đổi sau boot.
7. **VM running nghĩa workload đã sẵn sàng.** Attestation và readiness của ứng dụng là hai điều kiện khác nhau.
8. **vTPM giống TPM vật lý.** Mức bảo vệ phụ thuộc hypervisor, nhà cung cấp và trust model.
9. **Confidential VM tự động đáng tin cậy.** Cần xác minh report, TCB, measurement và policy.
10. **PCR khác baseline luôn là tấn công.** Update hợp lệ cũng làm PCR thay đổi; cần quản lý baseline theo phiên bản.
11. **Attestation pass có thể cấp mọi secret.** Secret vẫn cần scope, audience, identity, thời hạn và least privilege.
12. **Verifier lỗi thì nên cho phép truy cập để tăng availability.** Với tài nguyên nhạy cảm, fail-open có thể vô hiệu hóa toàn bộ kiểm soát attestation.

### Attestation không phải chứng nhận chất lượng phần mềm

Một môi trường có boot chain hợp lệ vẫn có thể chạy ứng dụng có lỗ hổng, cấu hình sai hoặc logic không an toàn. Attestation là một tín hiệu về trạng thái được đo và nguồn gốc của môi trường, không phải bằng chứng mọi dòng code đều đúng.

## 15. Ví dụ: chỉ cấp secret cho VM có boot state được duyệt

Một dịch vụ nội bộ chỉ cho VM production lấy secret kết nối database. Nhóm nền tảng đã chuẩn hóa image, bật Secure Boot và measured boot, đồng thời đăng ký reference values theo loại VM.

Luồng xử lý:

1. VM production khởi động từ image version đã phê duyệt.
2. Agent trên VM yêu cầu verifier tạo challenge.
3. Verifier gửi nonce duy nhất.
4. Agent yêu cầu TPM tạo quote cho tập PCR được policy chọn.
5. VM gửi quote, event log và danh tính workload tới verifier.
6. Verifier xác minh chữ ký, nonce, event log và reference values.
7. Verifier kiểm tra image/firmware version có trong policy production.
8. Nếu pass, verifier phát token ngắn hạn có audience là secret manager.
9. Secret manager xác minh token và workload identity.
10. Secret manager cấp đúng secret với thời hạn và quyền tối thiểu.
11. Nếu fail hoặc indeterminate, VM không nhận secret và được giữ ngoài traffic nhạy cảm.

### Chính sách minh họa

~~~yaml
attestation_policy:
  id: production-vm-policy
  version: "3"
  subject:
    environment: production
    workload: payments-api
  requirements:
    secure_boot: enabled
    measured_boot: required
    tpm_quote: required
    fresh_nonce: required
    event_log_replay: required
    reference_values:
      - image-release-2026.11
      - firmware-profile-prod-v2
  decision:
    pass: allow_scoped_secret
    fail: deny_and_quarantine
    indeterminate: deny_sensitive_access
  token:
    audience: secret-manager
    max_ttl_seconds: 300
~~~

Đây là policy minh họa, không phải schema chuẩn của một nhà cung cấp. Trong production, cần ràng buộc policy với danh tính khóa attestation, PCR profile, thuật toán, TCB status, region/account và nguồn reference values.

### Kiểm tra trên Linux

Trên hệ thống có TPM 2.0 và bộ công cụ tpm2-tools, một số lệnh quan sát cơ bản:

~~~sh
# Xem thiết bị TPM và trạng thái PCR
ls -l /dev/tpm*
tpm2_getcap properties-fixed
tpm2_pcrread sha256:0,2,4,7
~~~

Các PCR trong ví dụ chỉ là nhóm thường được kiểm tra trên một số profile PC/UEFI. Không dùng cùng danh sách cho mọi cloud VM. Hãy xác định PCR selection theo firmware profile và policy của nền tảng.

Có thể kiểm tra trạng thái Secure Boot bằng công cụ phù hợp của bản phân phối, ví dụ:

~~~sh
mokutil --sb-state
~~~

Lệnh này kiểm tra trạng thái Secure Boot theo môi trường hỗ trợ; nó không thay thế TPM quote hoặc remote attestation.

Event log TPM có thể được cung cấp qua firmware interface hoặc công cụ của hệ điều hành. Đường dẫn và định dạng phụ thuộc kernel, firmware và image. Dùng công cụ tương thích để thu log, sau đó replay cùng quote trong verifier.

## 16. Quy trình triển khai measured boot và attestation

Một lộ trình triển khai có kiểm soát:

1. **Xác định threat model:** bảo vệ trước thay đổi firmware, bootloader, kernel, host hay runtime nào?
2. **Chọn trust anchor:** TPM vật lý, vTPM, dịch vụ attestation của nền tảng hoặc TEE.
3. **Chọn profile đo:** PCR, event log, thuật toán hash và thành phần cần kiểm tra.
4. **Chuẩn hóa image:** firmware mode, Secure Boot, bootloader, kernel và cấu hình boot.
5. **Thu baseline:** đo từ môi trường sạch đã kiểm thử, không học tự động từ production bất kỳ.
6. **Xây verifier:** xác minh trust chain, quote, nonce, event log và reference values.
7. **Định nghĩa policy:** pass/fail/indeterminate, phạm vi subject, audience và thời hạn.
8. **Tích hợp relying party:** secret manager, workload identity, load balancer hoặc control plane.
9. **Canary:** bật attestation ở nhóm nhỏ, quan sát false reject và độ trễ.
10. **Mở rộng:** rollout theo môi trường, region và loại VM.
11. **Vận hành baseline:** cập nhật, thu hồi và rollback có phê duyệt.
12. **Diễn tập sự cố:** quote bất thường, TPM unavailable, verifier outage và firmware update.

### Các tiêu chí nghiệm thu

- VM tạo được quote từ TPM/attestation service đã đăng ký.
- Verifier phát hiện được quote sai chữ ký hoặc sai nonce.
- Event log replay khớp PCR trong trường hợp hợp lệ.
- Thay đổi boot component không được phê duyệt làm policy fail.
- Bản cập nhật hợp lệ được thêm baseline qua quy trình phê duyệt.
- Secret manager từ chối token hết hạn, sai audience hoặc subject.
- Trạng thái indeterminate không dẫn đến cấp quyền nhạy cảm.
- Audit log đủ thông tin điều tra nhưng không chứa secret.
- Có kế hoạch phục hồi khi verifier hoặc dịch vụ reference values không khả dụng.

## 17. Checklist vận hành

- [ ] Đã xác định root of trust và trust boundary của VM.
- [ ] Đã phân biệt Secure Boot, measured boot và attestation.
- [ ] Đã bật và kiểm tra TPM/vTPM hoặc cơ chế attestation phù hợp.
- [ ] Đã chọn PCR profile và thuật toán hash đúng nền tảng.
- [ ] Đã thu event log và xác minh khả năng replay.
- [ ] Quote có chữ ký hợp lệ và gắn với nonce mới.
- [ ] Đã xác minh chuỗi chứng thư của Attestation Key hoặc report.
- [ ] Reference values có nguồn gốc, version và người phê duyệt.
- [ ] Policy xử lý rõ pass, fail và indeterminate.
- [ ] Đã phân biệt boot measurement với runtime integrity.
- [ ] Confidential VM được kiểm tra TCB và report theo đúng trust model.
- [ ] Secret token có subject, audience và expiry ngắn.
- [ ] Relying party xác minh token trước khi cấp quyền.
- [ ] Đã có quy trình cập nhật, thu hồi và rollback baseline.
- [ ] Đã theo dõi tỷ lệ fail, latency, chứng thư và verifier health.
- [ ] Đã thử tình huống replay, log sai, firmware drift và verifier outage.
- [ ] Có quy trình cách ly hoặc reimage máy không đạt policy.
- [ ] Audit log không chứa private key, secret hoặc token đầy đủ.

## Kết luận

Measured boot ghi nhận trạng thái các thành phần khởi động bằng phép đo mật mã trong PCR; event log cung cấp ngữ cảnh để diễn giải các phép đo; TPM quote giúp bên xác minh kiểm tra trạng thái và freshness. Remote attestation kết hợp các bằng chứng đó với reference values và policy để quyết định một VM có được cấp secret hoặc tham gia workload nhạy cảm hay không. Secure Boot giúp ngăn thành phần boot không được tin cậy, còn confidential computing bổ sung cơ chế bảo vệ bộ nhớ và bằng chứng riêng theo phần cứng. Khi triển khai, cần quản lý baseline có nguồn gốc, phân biệt boot với runtime, xử lý rõ trạng thái indeterminate và tích hợp attestation với danh tính workload, quyền tối thiểu và giám sát vận hành.
