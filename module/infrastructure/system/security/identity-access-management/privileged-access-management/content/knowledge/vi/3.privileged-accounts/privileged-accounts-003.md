# Shared admin account

## 1. Tài khoản quản trị dùng chung là gì?

**Shared admin account** là tài khoản đặc quyền trên một hệ thống đích được nhiều người sử dụng để thực hiện công việc quản trị. Ví dụ, nhiều kỹ sư cùng đăng nhập bằng một tài khoản quản trị cục bộ trên thiết bị, một tài khoản quản trị của ứng dụng cũ hoặc một tài khoản có quyền cao trong cơ sở dữ liệu.

Điểm “dùng chung” nằm ở **principal tại hệ thống đích**: các hoạt động có thể cùng xuất hiện dưới một tên tài khoản, dù người khởi tạo khác nhau. Tài khoản đó có thể được dùng bằng cách chia sẻ mật khẩu trực tiếp hoặc được PAM quản lý để mở phiên cho từng người.

PAM — Privileged Access Management — cần kiểm soát ai được sử dụng tài khoản, dùng vào việc gì, trên tài nguyên nào, trong bao lâu và hoạt động được ghi nhận như thế nào. Đưa một mật khẩu dùng chung vào vault là một phần của việc quản lý, nhưng chưa tự giải quyết được toàn bộ vấn đề cấp quyền, truy vết và thu hồi.

### Ví dụ cơ bản

Một thiết bị chỉ có tài khoản quản trị đích tên `device-admin`. Ba kỹ sư vận hành đều cần quản trị thiết bị này.

- Nếu cả ba biết cùng mật khẩu và đăng nhập trực tiếp, nhật ký tại đích có thể chỉ ghi `device-admin`.
- Nếu mỗi kỹ sư xác thực bằng danh tính cá nhân vào PAM, rồi PAM mở phiên đến tài khoản đích, hệ thống có thể liên kết phiên với người khởi tạo nếu các nguồn bằng chứng được thiết kế đầy đủ.
- Trong cả hai trường hợp, tài khoản tại đích vẫn là tài khoản dùng chung. Mức độ kiểm soát khác nhau nằm ở cách cấp truy cập, quản lý credential, giới hạn đường sử dụng và liên kết hoạt động.

Vì vậy, cần phân biệt **tài khoản đích dùng chung** với **mật khẩu được chia sẻ tự do**. Có thể phải giữ một tài khoản đích dùng chung vì giới hạn nền tảng, nhưng không nên vì thế chấp nhận việc ai cũng biết và sử dụng credential ngoài kiểm soát.

## 2. Những trường hợp dễ bị nhầm lẫn

| Trường hợp | Có phải shared admin account không? | Điểm cần hiểu |
|---|---|---|
| Mỗi người có tài khoản riêng, cùng thuộc nhóm quản trị | Không chỉ vì cùng nhóm hoặc role | Principal tại đích vẫn khác nhau; quyền có thể giống nhau |
| Nhiều người dùng cùng một tài khoản quản trị đích | Có | Cần cơ chế liên kết hoạt động với từng người |
| Mỗi người vào PAM bằng tài khoản riêng nhưng dùng chung tài khoản đích | Có ở hệ thống đích | PAM có thể bổ sung liên kết cá nhân, không làm tài khoản đích trở thành nhiều tài khoản |
| Tài khoản chỉ dành cho một workload nhưng có nhiều người làm chủ sở hữu vận hành | Không tự động là tài khoản quản trị dùng chung của con người | Chủ sở hữu và chủ thể trực tiếp sử dụng là hai khái niệm khác nhau |
| Tài khoản dịch vụ bị nhiều người dùng để đăng nhập sửa lỗi | Có hiện tượng dùng lẫn giữa con người và workload | Cần tách mục đích, quyền và vòng đời |
| Tài khoản khẩn cấp do nhiều người có thể được phép sử dụng khi cần | Có thể là tài khoản dùng chung | Phải kiểm soát điều kiện kích hoạt và người sử dụng thực tế |
| Nhiều người có cùng tên tài khoản trên các hệ thống độc lập | Chưa đủ thông tin để kết luận | Cần biết principal, credential và phạm vi hệ thống thực tế |

Một trường hợp khác là người dùng đăng nhập bằng tài khoản cá nhân rồi chuyển sang ngữ cảnh đặc quyền chung trên hệ điều hành. Cần xem hệ thống có giữ được liên kết giữa người đăng nhập, thao tác nâng quyền và các hoạt động sau đó hay không. Chỉ thấy tên tài khoản có quyền cao trong log cuối cùng sẽ chưa đủ để kết luận toàn bộ chuỗi đã được truy vết.

## 3. Vì sao tài khoản quản trị dùng chung có rủi ro cao?

### 3.1. Khó xác định ai đã thực hiện hành động

Nếu nhiều người biết cùng credential, một sự kiện mang tên tài khoản đích không tự chỉ ra người thao tác. Địa chỉ IP cũng chưa đủ nếu nhiều người truy cập qua cùng máy trung gian hoặc địa chỉ NAT.

Việc biết “ai đã lấy mật khẩu từ vault” hỗ trợ điều tra, nhưng không tự chứng minh rằng người đó là người đã thực hiện mọi thao tác sau này. Credential có thể được sao chép, dùng ở nơi khác hoặc tiếp tục được sử dụng sau thời gian đã khai báo.

### 3.2. Khó thu hồi riêng một người

Với tài khoản cá nhân, có thể thu hồi principal hoặc role của một người. Với credential dùng chung đã được nhiều người biết, việc xóa quyền truy cập vault của một cá nhân không xóa bản sao credential mà họ đã có.

Muốn loại bỏ khả năng dùng lại credential đó, cần xem xét luân chuyển hoặc vô hiệu hóa tại hệ thống đích, đồng thời xử lý các yếu tố xác thực, token, khóa và phiên liên quan. Việc này có thể ảnh hưởng đến những người vẫn có nhu cầu hợp lệ.

### 3.3. Quyền thường rộng hơn nhiệm vụ

Một tài khoản dùng chung thường được tạo để đáp ứng nhiều loại công việc. Người chỉ cần khởi động lại một dịch vụ có thể vì thế nhận khả năng sửa hệ thống, đọc secret hoặc tạo tài khoản mới.

Dùng chung không bắt buộc phải toàn quyền, nhưng cách tổ chức này dễ dẫn đến role được thiết kế theo tổng nhu cầu của cả nhóm thay vì nhu cầu cụ thể của từng phiên.

### 3.4. Credential lan sang nhiều nơi

Mật khẩu có thể đi vào tệp ghi chú, công cụ kết nối, script, kho mã hoặc hội thoại. Càng nhiều bản sao không được quản lý, việc xác định ai còn khả năng sử dụng và credential đã lộ ở đâu càng khó.

Nếu một credential còn được dùng lại trên nhiều máy hoặc nhiều môi trường, việc mất một bản sao có thể tạo ảnh hưởng trên toàn bộ các tài nguyên liên quan.

### 3.5. Truy cập đồng thời làm việc liên kết phức tạp hơn

Hai người cùng sử dụng tài khoản đích tại một thời điểm có thể tạo các thay đổi đan xen. Nếu log không có định danh phiên đủ rõ, rất khó gắn từng hành động với một người.

Ngoài vấn đề truy vết, các thao tác đồng thời còn có thể ghi đè cấu hình, làm gián đoạn công việc của nhau hoặc tạo hiểu nhầm khi khôi phục.

### 3.6. Thay đổi credential có thể gây gián đoạn

Một mật khẩu tưởng chỉ dành cho quản trị thủ công có thể đang được script hoặc công cụ giám sát sử dụng. Luân chuyển mà không kiểm kê phụ thuộc có thể làm hỏng tác vụ hợp lệ.

Rủi ro vận hành không phải lý do để giữ nguyên credential vô thời hạn. Nó là lý do phải phân tách mục đích sử dụng, hiểu phụ thuộc và thiết kế quy trình luân chuyển có xác nhận.

## 4. Khi nào cần thay thế và khi nào phải quản lý ngoại lệ?

Hướng thiết kế thường mong muốn là dùng danh tính cá nhân hoặc cơ chế cấp quyền theo từng chủ thể khi nền tảng hỗ trợ. Tài khoản cá nhân kết hợp role phù hợp giúp quản lý vòng đời và liên kết trách nhiệm rõ hơn.

Tuy nhiên, một số hệ thống cũ, thiết bị hoặc quy trình khôi phục có giới hạn tài khoản và tích hợp. Khi chưa thể loại bỏ tài khoản dùng chung, cần quản lý nó như một ngoại lệ có chủ sở hữu, phạm vi và kiểm soát rõ ràng.

| Tình huống | Hướng xử lý nên xem xét |
|---|---|
| Hệ thống hỗ trợ đầy đủ tài khoản cá nhân và role phù hợp | Chuyển sang principal cá nhân hoặc cấp quyền theo danh tính |
| Chỉ cần một số tác vụ được xác định | Cung cấp cơ chế tác vụ hoặc endpoint quản trị hạn chế nếu khả thi |
| Hệ thống chỉ hỗ trợ tài khoản đích dùng chung | Kiểm soát qua PAM, giảm lộ credential và bổ sung truy vết |
| Tài khoản tồn tại nhưng không còn mục đích hợp lệ | Xác minh phụ thuộc, thu hồi và loại bỏ theo kế hoạch |
| Tài khoản dùng lẫn cho người và tự động hóa | Tách danh tính workload khỏi luồng quản trị của con người |
| Tài khoản dành cho khôi phục khẩn cấp | Giữ theo kịch bản phục hồi được xác định, hạn chế dùng thường ngày |

Một ngoại lệ cần có lý do cụ thể và điều kiện xem xét lại. “Nhóm vẫn dùng như vậy từ trước” không mô tả được nhu cầu kỹ thuật, phạm vi rủi ro hoặc trách nhiệm quản lý.

Không nên vô hiệu hóa một tài khoản quản trị sẵn có khi chưa biết nó có phải đường khôi phục cần thiết hay không. Việc thay thế phải bảo đảm có đường truy cập quản trị hợp lệ và phương án phục hồi phù hợp.

## 5. Kiểm kê trước khi đưa vào PAM

Trước khi thay đổi cách sử dụng một tài khoản, cần biết chính xác nó tồn tại ở đâu và ai đang phụ thuộc vào nó.

| Nhóm thông tin | Nội dung cần làm rõ |
|---|---|
| Principal đích | Tài khoản nào, thuộc thiết bị, ứng dụng hoặc miền quản trị nào |
| Chủ sở hữu | Người hoặc nhóm chịu trách nhiệm về mục đích, quyền và vòng đời |
| Người sử dụng | Những cá nhân hoặc nhóm được phép yêu cầu truy cập |
| Phạm vi quyền | Hành động, tài nguyên, dữ liệu và khả năng cấp thêm quyền |
| Đường truy cập | CLI, web, API, console, công cụ quản trị hoặc các đường khác |
| Credential | Loại credential, nơi quản lý, ai có thể đã biết hoặc giữ bản sao |
| Mục đích | Quản trị thường ngày, bảo trì, hỗ trợ hoặc truy cập khẩn cấp |
| Phụ thuộc | Script, công cụ hoặc dịch vụ đang dùng cùng principal hoặc credential |
| Phiên và token | Cách phát hành, thời hạn, khả năng liệt kê và chấm dứt |
| Bằng chứng | Nhật ký hiện có và khả năng liên kết người với hoạt động |
| Phục hồi | Cách khôi phục nếu thay credential hoặc cấu hình truy cập thất bại |
| Kế hoạch thay thế | Có thể chuyển sang tài khoản cá nhân hoặc cơ chế tác vụ khi nào |

**Chủ sở hữu tài khoản** không đồng nghĩa với người thực hiện mọi hành động bằng tài khoản đó. Chủ sở hữu chịu trách nhiệm về vòng đời và phạm vi; mỗi lần sử dụng vẫn cần liên kết với người hoặc workload thực tế.

Ví dụ một hồ sơ khái niệm:

```json
{
  "accountRef": "legacy-appliance-admin",
  "accountType": "shared-human-admin",
  "targetRef": "appliance-cluster-a",
  "ownerRef": "team-platform",
  "allowedRequesterGroup": "approved-platform-operators",
  "usePurpose": "approved-maintenance",
  "credentialRef": "managed-reference-only",
  "accessMode": "brokered-session",
  "knownAutomationDependencies": [],
  "reviewCondition": "when-target-supports-individual-administration"
}
```

Đây là dữ liệu minh họa, không phải schema của sản phẩm PAM hay policy thực thi. Danh sách phụ thuộc rỗng chỉ có ý nghĩa sau khi đã kiểm kê phù hợp; việc ghi rỗng không tự chứng minh không có công cụ nào sử dụng tài khoản.

Không lưu giá trị mật khẩu, token hoặc khóa riêng trong hồ sơ kiểm kê.

## 6. Hai cách cung cấp quyền sử dụng tài khoản

### 6.1. PAM môi giới phiên, hạn chế hiển thị credential

Người dùng xác thực bằng danh tính cá nhân, gửi yêu cầu phù hợp và được PAM mở phiên tới hệ thống đích. Khi tích hợp cho phép, PAM sử dụng credential mà không hiển thị trực tiếp cho người dùng.

```text
Người vận hành cụ thể
    -> Xác thực cá nhân và kiểm tra điều kiện
    -> Yêu cầu tác vụ, tài nguyên và thời gian
    -> Quyết định cấp truy cập
    -> PAM mở phiên bằng tài khoản đích dùng chung
    -> Ghi nhận người khởi tạo, phiên và thao tác
    -> Kết thúc truy cập theo cơ chế đã thiết kế
```

Cách này giảm nhu cầu sao chép mật khẩu và tạo điểm liên kết giữa danh tính cá nhân với phiên đặc quyền.

Tuy nhiên, cần hiểu giới hạn:

- Người trong phiên vẫn có thể lạm dụng những quyền mà tài khoản đích cho phép.
- Một số tác vụ hoặc giao thức có thể không đi qua cơ chế môi giới đó.
- Đường đăng nhập trực tiếp bằng credential đã biết từ trước có thể vẫn tồn tại.
- Tài khoản có quyền cao có thể tạo tài khoản mới, token hoặc đường truy cập khác nếu không bị giới hạn.
- Ghi hình phiên không tự ngăn thao tác phá hoại hoặc bảo đảm quan sát được mọi hành động.

### 6.2. Cấp credential để người dùng đăng nhập trực tiếp

Một số trường hợp buộc người vận hành nhận credential, thường được gọi là **credential checkout** hoặc nhận secret để sử dụng trong khoảng thời gian cho phép.

Cần quản lý việc ai được lấy, lấy cho tài nguyên nào, lý do, thời gian và điều kiện xử lý sau sử dụng. Tuy nhiên, thời hạn ghi trên yêu cầu không tự khiến mật khẩu ngừng hoạt động tại đích.

Sau khi credential đã được hiển thị, phải giả định nó có thể được sao chép. Việc người dùng “trả lại” credential hoặc bấm kết thúc yêu cầu không xóa được bản sao. Khả năng dùng lại chỉ thay đổi khi có cơ chế thực sự như thay credential tại đích, vô hiệu hóa khả năng xác thực liên quan hoặc giới hạn bằng cơ chế của nền tảng.

| Tiêu chí | Môi giới phiên, không hiển thị credential khi khả thi | Hiển thị credential để truy cập |
|---|---|---|
| Khả năng sao chép mật khẩu | Giảm trong luồng được môi giới | Người nhận có thể sao chép giá trị |
| Liên kết người với phiên | Có thể được tạo ngay tại điểm mở phiên | Cần đối chiếu thêm với sự kiện tại đích |
| Sử dụng ngoài đường PAM | Cần chặn các đường còn tồn tại | Dễ phát sinh nếu credential được dùng trực tiếp |
| Xử lý kết thúc | Dừng phiên và quyền theo cơ chế thực tế | Cần tính cả credential đã biết, phiên và token phát sinh |
| Phạm vi quyền | Vẫn phải giới hạn tài khoản hoặc tác vụ | Vẫn phải giới hạn tài khoản hoặc tác vụ |

Không nên tuyên bố một cách truy cập an toàn chỉ vì có tên tính năng PAM. Cần đánh giá đường đi, quyền tại đích và khả năng thu hồi thực tế.

## 7. Các kiểm soát cần phối hợp

### 7.1. Xác thực từng người trước khi cấp đặc quyền

Mỗi người cần sử dụng danh tính cá nhân với cơ chế xác thực phù hợp mức rủi ro. Quy trình đăng ký, thay đổi và khôi phục yếu tố xác thực cũng phải được bảo vệ.

Chia sẻ thêm một yếu tố xác thực của tài khoản đích cho cả nhóm không tự giải quyết việc xác định người sử dụng. Nếu nền tảng cần yếu tố chung, cần kiểm soát việc sử dụng qua luồng gắn với danh tính cá nhân và hiểu các đường có thể bỏ qua luồng đó.

### 7.2. Least privilege và JEA

**Least privilege** là chỉ cấp quyền cần thiết cho nhiệm vụ. **JEA — just-enough administration** giới hạn khả năng quản trị ở đúng tác vụ cần làm.

Nếu tài khoản dùng chung có thể được giới hạn role, cần thu hẹp quyền theo mục đích. Nếu không thể tách đủ tại đích, có thể xem xét endpoint tác vụ hoặc cơ chế kiểm soát phù hợp mà nền tảng hỗ trợ.

Các giới hạn phải xét cả tham số, thực thi mã, khả năng đọc secret và đường tự nâng quyền. Một danh sách lệnh ngắn vẫn có thể rất mạnh nếu một lệnh cho phép chạy script tùy ý.

### 7.3. JIT và thời hạn sử dụng

**JIT — just-in-time access** giới hạn thời điểm có thể yêu cầu hoặc sử dụng đặc quyền. Ví dụ, một người được mở phiên quản trị cho nhiệm vụ bảo trì trong cửa sổ đã xác định.

Cần phân biệt:

- Thời hạn được phép gửi yêu cầu hoặc lấy credential.
- Thời hạn role tại hệ thống quản lý.
- Thời hạn credential hoặc token tại đích.
- Thời gian tồn tại của phiên đang hoạt động.

Các thời hạn này không mặc nhiên trùng nhau. Muốn tuyên bố truy cập kết thúc đúng hạn, phải biết cơ chế nào dừng từng khả năng liên quan.

### 7.4. Giới hạn đường truy cập

PAM cần được phối hợp với các kiểm soát tại đích và đường kết nối để hạn chế đăng nhập ngoài luồng dự kiến. Phải xét cả web, API, CLI, console và công cụ tự động hóa.

Một tường lửa giới hạn nguồn kết nối có thể giảm nơi truy cập, nhưng địa chỉ nguồn không thay thế danh tính cá nhân. Ngược lại, có danh tính cá nhân ở PAM cũng chưa đủ nếu credential đích vẫn dùng được tự do từ nơi khác.

### 7.5. Phân tách quyền quản trị PAM và bằng chứng

Người được dùng tài khoản đích không nên mặc nhiên được sửa policy cấp credential, mở rộng nhóm người dùng hoặc xóa nhật ký trung tâm. Tài khoản quản trị vault và hệ thống môi giới phiên cũng cần được kiểm soát vì có thể ảnh hưởng nhiều tài khoản đích.

Mức phân tách và phê duyệt cần phù hợp với rủi ro. Không phải mọi thao tác đều cần nhiều người duyệt, nhưng một người tự cấp quyền rộng, sử dụng rồi xóa dấu vết là tổ hợp khả năng cần tránh.

## 8. Truy cập đồng thời và ý nghĩa của checkout/check-in

### 8.1. Khóa nhận credential chưa phải khóa mọi phiên

Một vault có thể cho phép chỉ một người nhận credential tại một thời điểm. Điều đó giúp kiểm soát việc cấp secret trong luồng đó, nhưng không tự ngăn:

- Người đã biết mật khẩu từ trước đăng nhập trực tiếp.
- Một phiên cũ tiếp tục hoạt động sau khi kết thúc checkout.
- Công cụ tự động hóa dùng cùng tài khoản.
- Token hoặc khóa khác cùng xác thực được vào principal.
- Người dùng mở nhiều kết nối sau khi đã nhận credential.

Vì vậy, cần phân biệt **khóa cấp credential** với **kiểm soát truy cập đồng thời tại đích**.

### 8.2. Khi buộc phải có nhiều phiên

Nếu nền tảng hỗ trợ nhiều phiên cùng tài khoản, cần định danh được từng phiên và liên kết với từng người. Nhật ký tại PAM và tại đích phải có đủ thông tin để đối chiếu, không chỉ dựa vào một khoảng thời gian rộng.

Có thể cần giới hạn một số hoạt động thay đổi để tránh xung đột, hoặc tách phiên theo nhiệm vụ. Giải pháp cụ thể phụ thuộc thiết bị, ứng dụng và cơ chế quản lý phiên.

### 8.3. Check-in không xóa credential khỏi trí nhớ hoặc thiết bị

**Check-in** thường biểu thị người dùng trả quyền sử dụng theo quy trình. Nó không phải bằng chứng rằng mọi bản sao secret đã biến mất.

Nếu quy trình cần ngăn dùng lại mật khẩu sau sử dụng, phải có thao tác thay credential hoặc cơ chế tương ứng tại đích và kiểm chứng kết quả. Đồng thời, cần xử lý các phiên hoặc token được tạo trong thời gian sử dụng; chỉ thay mật khẩu có thể chưa đủ.

## 9. Luân chuyển credential mà không tạo ra trạng thái mơ hồ

Luân chuyển là thay credential theo chính sách hoặc sự kiện, chẳng hạn sau khi một người đã biết mật khẩu không còn quyền, sau khi nghi lộ hoặc khi kết thúc một lần sử dụng cần xử lý.

Một quy trình hợp lý phải phân biệt được các bước:

1. **Chuẩn bị:** xác định phụ thuộc, phiên đang hoạt động, khả năng phục hồi và cơ chế thay credential được hỗ trợ.
2. **Thực hiện thay đổi:** dùng cơ chế được quản lý để thay credential tại hệ thống đích và cập nhật đối tượng quản lý tương ứng.
3. **Xác minh đồng bộ:** kiểm tra credential được quản lý có thể sử dụng theo yêu cầu và trạng thái thu hồi credential cũ phù hợp cơ chế của đích.
4. **Xác nhận phụ thuộc:** kiểm tra các công cụ hợp lệ đã được cập nhật hoặc đã dùng cơ chế nhận credential phù hợp.
5. **Ghi nhận kết quả:** lưu sự kiện và trạng thái thành công hoặc lỗi mà không ghi giá trị bí mật.
6. **Xử lý phần còn lại:** xem xét phiên, token, khóa và khả năng duy trì truy cập đã phát sinh.

Thứ tự cập nhật chi tiết phụ thuộc khả năng của nền tảng và cơ chế tích hợp. Điểm cần đạt là không đánh dấu hoàn thành chỉ vì một phía đã thay đổi.

| Trạng thái lỗi | Hệ quả có thể xảy ra | Điều cần xử lý |
|---|---|---|
| Vault đã cập nhật nhưng đích chưa thay credential | Credential được quản lý có thể không dùng được; credential cũ vẫn còn hiệu lực | Xác minh trạng thái hai phía và hòa giải theo quy trình |
| Đích đã thay nhưng vault chưa cập nhật đúng | Người hợp lệ mất đường truy cập được quản lý | Khôi phục khả năng truy cập bằng cơ chế được kiểm soát |
| Credential mới hoạt động nhưng phụ thuộc chưa cập nhật | Tác vụ hợp lệ thất bại | Xử lý phụ thuộc và theo dõi dịch vụ |
| Mật khẩu đã thay nhưng phiên cũ tiếp tục tồn tại | Đối tượng vẫn có thể thao tác trong phiên | Dừng hoặc xử lý phiên theo khả năng của hệ thống |
| Chỉ thay mật khẩu, bỏ sót khóa hoặc token khác | Đường truy cập khác vẫn còn | Kiểm kê và thu hồi đúng loại credential |

Nếu không thể luân chuyển ngay, cần ghi rõ lý do, phạm vi credential có thể đã lộ, giới hạn tạm thời, người chịu trách nhiệm và điều kiện xử lý tiếp. Không nên mô tả trạng thái chưa được xác minh là “đã thu hồi hoàn toàn”.

## 10. Vòng đời tài khoản quản trị dùng chung

### 10.1. Khi đưa tài khoản vào quản lý

Cần xác định quyền hiện có, các người dùng và những nơi credential đã được phân phối. Việc thêm một bản sao mật khẩu vào vault không làm các bản sao cũ mất hiệu lực.

Sau khi đã chuẩn bị phụ thuộc và đường phục hồi, cần xử lý credential đã biết từ trước theo kế hoạch phù hợp. Đồng thời, giới hạn đường truy cập và xác nhận khả năng mở phiên, ghi nhận, thu hồi.

### 10.2. Khi thêm hoặc thay đổi người sử dụng

Cấp quyền yêu cầu truy cập theo nhiệm vụ, thay vì gửi credential trực tiếp. Khi một người đổi nhóm, cần xem lại quyền đối với tài khoản dùng chung, các phiên hoặc token liên quan và credential mà họ từng được hiển thị.

Không nên để quyền tích lũy chỉ vì tài khoản đích được nhiều nhóm sử dụng.

### 10.3. Khi một người rời nhiệm vụ hoặc nghỉ việc

Thu hồi quyền của họ tại PAM hoặc hệ thống nhận dạng là một bước. Cần kiểm tra thêm:

- Họ có từng biết credential còn hiệu lực không?
- Có phiên đang mở, token hoặc khóa cá nhân nào còn được phép dùng không?
- Họ có thể tạo principal hoặc đường truy cập khác trong quá trình quản trị không?
- Credential có đang dùng lại trên tài nguyên khác không?
- Có phụ thuộc tự động hóa nào gắn với cách truy cập của họ không?

Không nhất thiết phải vô hiệu hóa tài khoản đích của cả nhóm trong mọi trường hợp. Cần lựa chọn cách khoanh vùng theo mức rủi ro và khả năng hệ thống, đồng thời bảo đảm quyền sử dụng hợp lệ vẫn được quản lý.

### 10.4. Khi tài khoản không còn cần thiết

Xác minh không còn nhiệm vụ hoặc phụ thuộc hợp lệ, bảo toàn bằng chứng cần thiết và loại bỏ các đường xác thực liên quan theo kế hoạch. Nếu tài khoản là thành phần tích hợp sẵn không thể xóa, cần áp dụng trạng thái và giới hạn mà nền tảng hỗ trợ.

Tài khoản phục hồi cần được xem xét theo kịch bản riêng, tránh loại bỏ đường khôi phục cần thiết hoặc để nó trở thành đường quản trị thường ngày không được quan sát.

## 11. Bằng chứng nào giúp truy vết đáng tin cậy?

Mục tiêu là nối được danh tính cá nhân với phạm vi quyền và hành động trên tài khoản dùng chung.

| Giai đoạn | Bằng chứng nên liên kết |
|---|---|
| Xác thực | Danh tính cá nhân, thời điểm, phương thức và kết quả |
| Yêu cầu | Tài khoản đích, tài nguyên, mục đích, thời hạn, mã công việc |
| Quyết định cấp quyền | Policy hoặc người phê duyệt, phạm vi được chấp thuận |
| Cấp credential hoặc mở phiên | Người nhận, định danh phiên, tài khoản đích, thời điểm |
| Hoạt động tại đích | Thao tác, tài nguyên bị tác động, kết quả và mã liên kết nếu có |
| Kết thúc | Trạng thái phiên, quyền và credential sau sử dụng |
| Luân chuyển hoặc thu hồi | Kết quả thực tế, lỗi nếu có, thời điểm và phụ thuộc liên quan |

Định danh phiên và thời gian nhất quán giúp đối chiếu các nguồn log. Bằng chứng cần được bảo vệ khỏi sửa, xóa trái phép và không chứa giá trị credential. Bản ghi phiên có thể chứa dữ liệu nhạy cảm nên cũng cần giới hạn quyền xem và sử dụng.

Ghi lại tài khoản cá nhân khởi tạo phiên hỗ trợ quy trách nhiệm nhưng không tự chứng minh người đó chủ ý thực hiện mọi hành động. Nếu nghi tài khoản cá nhân hoặc phiên bị chiếm dụng, điều tra phải xem xét thêm ngữ cảnh.

Khi log không đủ để phân biệt hai người dùng đồng thời hoặc không quan sát được một đường truy cập, cần ghi nhận mức độ chưa xác định. Không nên suy ra chắc chắn người thao tác chỉ từ danh sách những người được quyền lấy credential.

## 12. Ví dụ: nhóm vận hành dùng tài khoản quản trị của ứng dụng cũ

Một ứng dụng cũ chỉ có một tài khoản quản trị đầy đủ. Ba kỹ sư nội bộ và một chuyên gia nhà cung cấp có thể cần sử dụng nó. Trước đây, mật khẩu được gửi qua hội thoại và một script bảo trì cũng dùng cùng credential.

### Các vấn đề cần nhận diện

- Không biết những bản sao credential nào còn tồn tại.
- Tài khoản cung cấp nhiều quyền hơn một số nhiệm vụ hỗ trợ.
- Nhà cung cấp có thể tiếp tục dùng credential sau khi đợt hỗ trợ kết thúc.
- Nhật ký ứng dụng chỉ có tài khoản quản trị chung.
- Đổi mật khẩu ngay có thể làm hỏng script bảo trì.
- Khóa tài khoản đích có thể làm mọi người mất khả năng xử lý sự cố.

### Thiết kế chuyển đổi minh họa

| Việc cần làm | Kết quả mong muốn |
|---|---|
| Xác định chủ sở hữu tài khoản và từng người được phép sử dụng | Có trách nhiệm quản lý và danh sách người yêu cầu rõ ràng |
| Tách script sang danh tính workload phù hợp nếu nền tảng cho phép | Giảm phụ thuộc giữa truy cập con người và tự động hóa |
| Xử lý credential đã phân phối sau khi chuẩn bị phụ thuộc | Giảm khả năng dùng lại bản sao cũ |
| Mở phiên qua PAM bằng danh tính cá nhân | Liên kết người khởi tạo với phiên tại đích |
| Cấp quyền có thời hạn cho nhà cung cấp | Hạn chế truy cập ngoài đợt hỗ trợ |
| Hạn chế đường đăng nhập ngoài luồng được quản lý | Giảm khả năng dùng credential ngoài kiểm soát |
| Thu hẹp tác vụ nếu ứng dụng hoặc cơ chế trung gian hỗ trợ | Giảm quyền vượt nhu cầu |
| Ghi nhận sự kiện ứng dụng và hoạt động phiên | Bổ sung chuỗi bằng chứng |
| Lập kế hoạch thay ứng dụng hoặc nâng cấp mô hình tài khoản | Có hướng giảm dần ngoại lệ dùng chung |

Nếu không thể tách quyền chi tiết, nhóm phải ghi nhận giới hạn đó. Phê duyệt một phiên không biến tài khoản toàn quyền thành role chỉ hỗ trợ; các biện pháp bù đắp cần được mô tả đúng khả năng.

### Một sự kiện cần xử lý

Chuyên gia nhà cung cấp kết thúc đợt hỗ trợ. Trong lần làm việc trước, hệ thống buộc phải hiển thị mật khẩu để họ thực hiện một tác vụ chưa được môi giới.

Chỉ xóa quyền vào PAM của chuyên gia chưa đủ để loại bỏ khả năng dùng mật khẩu đã biết. Cần xử lý credential đó tại đích theo kế hoạch, thu hồi các phương tiện xác thực liên quan và xem xét phiên hoặc token còn tồn tại. Đồng thời, kiểm tra tác động đến người dùng hợp lệ và công cụ phụ thuộc.

Nếu sau đó phát hiện thay đổi không rõ nguồn gốc, cần đối chiếu phiên PAM, log ứng dụng và lịch sử thay đổi. Không nên kết luận người đã checkout gần nhất là thủ phạm khi vẫn có đường đăng nhập trực tiếp hoặc bản sao credential ngoài kiểm soát.

## 13. Kiểm chứng mô hình quản lý

Trong môi trường hoặc đợt diễn tập có phạm vi được cho phép, có thể đánh giá các yêu cầu sau:

| Tình huống | Kết quả mong đợi |
|---|---|
| Một người không thuộc phạm vi được cấp yêu cầu tài khoản | Bị từ chối và có sự kiện phù hợp |
| Người hợp lệ mở phiên cho đúng nhiệm vụ | Thành công, có liên kết cá nhân và tài khoản đích |
| Người dùng thử đi qua đường truy cập ngoài luồng dự kiến | Bị chặn hoặc được xử lý theo policy đã công bố |
| Hai người cùng dùng tài khoản theo mô hình cho phép | Có thể phân biệt phiên và hoạt động; nếu không cho đồng thời thì giới hạn được thực thi |
| Một người kết thúc checkout nhưng giữ bản sao mật khẩu | Quy trình xử lý credential tại đích ngăn dùng lại theo mục tiêu đã đặt |
| Quyền hết hạn khi phiên vẫn mở | Hành vi phiên khớp với cơ chế và mục tiêu được công bố |
| Luân chuyển thất bại một phía | Không đánh dấu thành công; có cảnh báo và quy trình hòa giải |
| Một người rời nhiệm vụ | Quyền, credential đã biết, phiên và token liên quan được xử lý phù hợp |
| Một thao tác cần điều tra | Có thể nối yêu cầu, danh tính, phiên và sự kiện tại đích trong phạm vi được quan sát |

Bảng này là gợi ý kiểm chứng cho người học, không phải tuyên bố các kiểm thử đã được thực hiện trên hệ thống thực tế.

Các chỉ số như số tài khoản đưa vào vault hoặc số lần luân chuyển chỉ phản ánh một phần công việc. Cần quan tâm thêm credential còn bị hiển thị ở đâu, đường đi vòng, khả năng liên kết phiên, kết quả thu hồi và các ngoại lệ chưa được xử lý.

## 14. Những cách hiểu cần tránh

- **“Vault có mật khẩu nên không còn ai truy cập ngoài PAM.”** Các bản sao cũ và đường đăng nhập trực tiếp có thể vẫn hoạt động.
- **“Người cuối cùng lấy mật khẩu chắc chắn là người gây thay đổi.”** Checkout không tự chứng minh chủ thể của mọi hành động tại đích.
- **“Check-in nghĩa là credential đã được trả lại hoàn toàn.”** Giá trị bí mật có thể đã được sao chép.
- **“Đổi mật khẩu là dừng mọi truy cập.”** Phiên, token, khóa hoặc principal mới có thể còn hiệu lực.
- **“MFA cho tài khoản chung là đủ xác định từng người.”** Cần danh tính cá nhân và liên kết hoạt động, không chỉ một yếu tố được nhiều người dùng.
- **“Tài khoản chỉ cho người quản trị dùng nên không cần kiểm kê phụ thuộc.”** Script hoặc công cụ có thể đang dùng cùng credential.
- **“Có ghi hình thì có thể giữ nguyên toàn quyền.”** Ghi nhận không thay thế giới hạn khả năng tác động.
- **“Chuyển sang tài khoản cá nhân là tự động đạt least privilege.”** Tài khoản cá nhân vẫn có thể có quyền quá rộng hoặc đường nâng quyền gián tiếp.

## 15. Tình huống tự luyện

Một nhóm có năm kỹ sư cùng dùng tài khoản `platform-admin`. Mỗi người đăng nhập vault bằng tài khoản cá nhân và có thể xem mật khẩu. Vault chỉ cho một người checkout tại một thời điểm. Hệ thống đích cho phép nhiều phiên đồng thời, có API token riêng và vẫn chấp nhận đăng nhập trực tiếp. Một nhân viên vừa chuyển nhóm.

Hãy phân tích:

1. Cơ chế checkout hiện tại có ngăn được mọi truy cập đồng thời không?
2. Vì sao xóa quyền vào vault của nhân viên chuyển nhóm chưa đủ trong mọi trường hợp?
3. Cần kiểm kê những credential, phiên và token nào trước khi thu hồi?
4. Bằng chứng nào cần có để phân biệt các hành động trong hai phiên cùng tài khoản?
5. Có thể chuyển phần nào sang danh tính cá nhân, role tạm thời hoặc tác vụ hạn chế?
6. Nếu luân chuyển mật khẩu làm một công cụ hợp lệ ngừng hoạt động, quy trình đã thiếu thông tin gì?

Gợi ý: bắt đầu từ principal đích, các phương tiện xác thực và mọi đường sử dụng, rồi mới xem giới hạn của checkout. Sau đó xác định người đã biết credential, phụ thuộc tự động hóa và khả năng liên kết hoạt động theo từng phiên.

## 16. Ghi nhớ

Tài khoản quản trị dùng chung tạo ra thách thức về liên kết cá nhân, giới hạn quyền và thu hồi. Khi nền tảng hỗ trợ, nên chuyển sang danh tính cá nhân hoặc cơ chế cấp quyền theo từng chủ thể và nhiệm vụ.

Khi phải giữ tài khoản đích dùng chung, cần quản lý toàn bộ luồng sử dụng: xác thực từng người, giới hạn người yêu cầu và tác vụ, kiểm soát credential, hạn chế đường đi vòng, xử lý truy cập đồng thời, ghi nhận bằng chứng và thu hồi có hiệu lực tại đích. PAM có giá trị khi các kiểm soát đó phối hợp được với nhau và các giới hạn còn lại được nhận diện rõ.
