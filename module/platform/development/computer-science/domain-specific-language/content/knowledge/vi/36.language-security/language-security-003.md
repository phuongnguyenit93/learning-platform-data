# Sandbox

Một ngôn ngữ chuyên biệt cho lĩnh vực (Domain-Specific Language — DSL) có thể cho phép người dùng mô tả quy tắc nghiệp vụ, truy vấn dữ liệu, workflow, công thức, cấu hình hoặc hành động tự động. Khi chương trình DSL được thực thi, nó có thể đọc dữ liệu, gọi dịch vụ, tạo file, gửi message hoặc thay đổi trạng thái của hệ thống. Nếu người viết DSL không hoàn toàn đáng tin cậy, việc thực thi trực tiếp trong tiến trình ứng dụng có thể tạo rủi ro nghiêm trọng.

**Sandbox** là môi trường thực thi được giới hạn nhằm kiểm soát những tài nguyên mà chương trình có thể truy cập và những hành động mà chương trình được phép thực hiện. Sandbox tạo một ranh giới bảo mật giữa mã DSL và hệ thống host. Mục tiêu là cho phép chương trình thực hiện đúng nhiệm vụ được giao trong phạm vi quyền hạn cụ thể, đồng thời hạn chế ảnh hưởng nếu chương trình có lỗi, bị khai thác hoặc cố ý thực hiện hành vi nguy hiểm.

Trong hệ sinh thái DSL, sandbox có thể nằm ở nhiều lớp. Interpreter có thể chỉ cung cấp một tập hàm được cho phép; runtime có thể giới hạn bộ nhớ và thời gian; process riêng có thể cô lập filesystem và network; container hoặc WebAssembly runtime có thể bổ sung ranh giới hệ điều hành. Những lớp này giải quyết các loại rủi ro khác nhau và không nên được xem là tương đương.

Sandbox không phải một công tắc bảo mật duy nhất. Nó là tập hợp các cơ chế gồm threat model, capability, policy, isolation, resource quota, validation, monitoring và quy trình xử lý sự cố. Thiết kế cần dựa trên mức độ tin cậy của tác giả DSL, dữ liệu mà chương trình xử lý, hậu quả của side effect và khả năng chịu lỗi của hệ thống.

Bài học này trình bày mục tiêu và ranh giới của sandbox, threat model cho DSL, các mức cô lập, capability-based security, kiểm soát filesystem và network, giới hạn tài nguyên, xử lý dữ liệu, giao tiếp với host, multi-tenancy, vận hành, kiểm thử và một ví dụ xây dựng sandbox cho DSL workflow.

## 1. Sandbox là gì?

Sandbox là môi trường chạy chương trình với quyền hạn và tài nguyên bị giới hạn. Chương trình có thể thực hiện một số thao tác được cho phép, nhưng không được tự do truy cập toàn bộ hệ thống.

Ví dụ, một DSL tính phí vận chuyển có thể được phép:
- Đọc trọng lượng và địa chỉ giao hàng đã được cung cấp.
- Sử dụng phép toán số học và hàm tính khoảng cách được cấp.
- Trả về một kết quả phí vận chuyển.
- Ghi diagnostic nếu dữ liệu đầu vào không hợp lệ.

Chương trình đó có thể không được phép:
- Đọc file bất kỳ trên máy chủ.
- Mở kết nối mạng tùy ý.
- Đọc biến môi trường chứa secret.
- Tạo process con.
- Ghi vào database ngoài API được cấp.
- Truy cập dữ liệu của tenant khác.
- Chạy vô hạn hoặc tiêu thụ bộ nhớ không giới hạn.

### 1.1. Sandbox và môi trường thực thi thông thường

Một chương trình host thông thường có thể thừa hưởng quyền của process đang chạy. Nếu process có quyền đọc thư mục cấu hình, mở network connection và truy cập database, mã được thực thi bên trong process có thể vô tình hoặc cố ý sử dụng những quyền đó.

Sandbox tạo một lớp kiểm soát riêng. Thay vì cho chương trình DSL tiếp cận trực tiếp với mọi API host, runtime chỉ cung cấp những capability được cấp cho lần chạy đó.

~~~text
DSL Program
    |
    v
Sandbox Runtime
    |
    +--> Allowed DSL Functions
    +--> Scoped Data Access
    +--> Resource Limits
    +--> Policy Enforcement
    |
    v
Host Services
    |
    +--> Database API
    +--> File Service
    +--> Message Service
    +--> External API
~~~

Chương trình DSL không nên nhận trực tiếp các đối tượng host có quyền rộng. Nó tương tác với facade hoặc capability hẹp, và lớp này kiểm tra quyền trước khi thực hiện thao tác.

### 1.2. Sandbox không chỉ là chạy trong process riêng

Một process riêng có thể giúp cô lập crash và address space, nhưng nếu process đó vẫn chạy cùng user hệ điều hành với quyền rộng, nó có thể đọc file hoặc truy cập network mà user đó được phép.

Tương tự, container giúp đóng gói và giới hạn một số tài nguyên, nhưng container mặc định không phải ranh giới tuyệt đối. Cần cấu hình user, namespace, filesystem, syscall, network, capability và runtime phù hợp.

### 1.3. Sandbox và trust boundary

Trust boundary là ranh giới giữa thành phần được tin cậy và thành phần có mức tin cậy thấp hơn. Với DSL, boundary thường nằm giữa:
- Source DSL do người dùng hoặc tenant cung cấp.
- Parser và compiler do nền tảng kiểm soát.
- Sandbox runtime.
- Host service có quyền truy cập dữ liệu.
- Hệ điều hành hoặc hạ tầng.

Parser và validator cũng cần được xem xét trong threat model vì source độc hại có thể khai thác lỗi parser hoặc tiêu thụ tài nguyên trước khi sandbox runtime bắt đầu.

## 2. Vì sao DSL cần sandbox?

DSL thường được thiết kế để người dùng nghiệp vụ có thể mô tả hành vi mà không cần viết một ứng dụng hoàn chỉnh. Chính khả năng biểu đạt đó có thể tạo ra quyền thực thi đáng kể.

### 2.1. DSL do người dùng cung cấp

Một nền tảng có thể cho phép khách hàng viết quy tắc, công thức hoặc workflow riêng. Nhà cung cấp không thể mặc định mọi chương trình đều an toàn.

Ví dụ:
- Một tenant tạo rule kiểm tra đơn hàng.
- Một người dùng tạo công thức báo cáo.
- Một nhóm vận hành tạo workflow tự động.
- Một plugin đóng góp action mới.
- Một hệ thống nhận DSL từ API hoặc file import.

Sandbox giới hạn tác động của chương trình ngay cả khi tác giả nhập biểu thức sai hoặc có ý định xấu.

### 2.2. Lỗi vô ý cũng có thể gây sự cố

Không phải mọi rủi ro đều đến từ kẻ tấn công. Một vòng lặp vô hạn, truy vấn quá rộng hoặc recursion không có giới hạn có thể làm cạn tài nguyên.

Ví dụ:

~~~text
while true {
  calculateNextValue()
}
~~~

Một DSL có thể không hỗ trợ vòng lặp vô hạn về mặt thiết kế, nhưng recursion, biểu thức lồng nhau hoặc truy vấn collection lớn vẫn có thể gây tiêu thụ tài nguyên quá mức.

### 2.3. Bảo vệ dữ liệu và tenant

Một rule của tenant A không được đọc dữ liệu tenant B. Một công thức chỉ cần một tập trường đầu vào không nên có khả năng truy vấn toàn bộ database.

Sandbox giúp giới hạn dữ liệu theo execution context, tenant, resource và capability.

### 2.4. Giảm ảnh hưởng của extension

DSL có thể cho phép plugin hoặc custom function. Nếu plugin chạy với toàn bộ quyền của host, một extension lỗi có thể làm lộ dữ liệu hoặc ảnh hưởng cả nền tảng.

Một extension API có capability hẹp và lifecycle được kiểm soát giúp giảm phạm vi tác động.

### 2.5. Hỗ trợ thực thi an toàn ở quy mô lớn

Khi có hàng nghìn chương trình do nhiều người dùng tạo, mỗi execution cần quota, timeout, isolation và telemetry riêng. Sandbox tạo cơ sở để nền tảng xử lý các chương trình không đồng nhất trong cùng hạ tầng.

## 3. Threat model cho DSL execution

Trước khi chọn công nghệ sandbox, cần xác định tài sản cần bảo vệ, tác nhân có thể gây rủi ro, đường tấn công và hậu quả.

### 3.1. Tài sản cần bảo vệ

- Source code và artifact của dự án.
- Dữ liệu nghiệp vụ và dữ liệu cá nhân.
- Credential, token và secret.
- Database và message broker.
- Filesystem của host.
- Network nội bộ.
- Tài nguyên CPU, memory và storage.
- Các tenant khác.
- Tính sẵn sàng và tính toàn vẹn của runtime.

### 3.2. Tác nhân và nguồn đầu vào

Nguồn DSL có thể đến từ:
- Người dùng cuối.
- Tenant hoặc tổ chức bên ngoài.
- Repository được import.
- Plugin hoặc extension.
- API tích hợp.
- Template hoặc code generator.
- Một workflow khác sinh ra DSL.

Mức tin cậy của từng nguồn có thể khác nhau. Một file do administrator ký duyệt có thể được phép dùng capability khác với biểu thức người dùng nhập trực tiếp.

### 3.3. Nhóm hành vi nguy hiểm

| Nhóm rủi ro | Ví dụ | Tác động |
| --- | --- | --- |
| Resource exhaustion | Vòng lặp lớn, recursion sâu, collection khổng lồ | Cạn CPU hoặc memory |
| Unauthorized data access | Đọc tenant khác hoặc field bị hạn chế | Rò rỉ dữ liệu |
| Filesystem access | Đọc secret hoặc ghi đè file | Lộ credential, hỏng dữ liệu |
| Network access | Gọi endpoint nội bộ hoặc exfiltrate dữ liệu | SSRF, rò rỉ thông tin |
| Host escape | Gọi reflection hoặc native API | Vượt sandbox |
| Side-effect abuse | Gửi message hoặc tạo giao dịch lặp | Thay đổi nghiệp vụ ngoài ý muốn |
| Denial of service | Tạo nhiều task hoặc request | Giảm tính sẵn sàng |
| Supply-chain risk | Plugin hoặc dependency độc hại | Xâm phạm runtime |

### 3.4. Trust assumption

Cần ghi rõ:
- DSL source có được xem là không đáng tin không?
- Compiler và runtime có thuộc trusted computing base không?
- Plugin được ký hay do người dùng tự tải?
- Host service có kiểm tra authorization độc lập không?
- Worker có thể bị compromise không?
- Sandbox có phải chịu trách nhiệm bảo vệ kernel không?

Một thiết kế tốt không giả định mọi lớp đều hoàn hảo. Nó giảm quyền, giới hạn tác động và phát hiện hành vi bất thường.

### 3.5. Security objective

Có thể đặt các mục tiêu:
1. Chỉ thực hiện capability được cấp.
2. Không truy cập dữ liệu ngoài phạm vi.
3. Không vượt quota tài nguyên.
4. Không thoát khỏi execution boundary.
5. Không để lỗi của một execution làm hỏng execution khác.
6. Có thể dừng và thu hồi execution.
7. Có audit và telemetry đủ để điều tra.

## 4. Các lớp sandbox và isolation

Không có một cơ chế duy nhất phù hợp mọi DSL. Có thể kết hợp nhiều lớp tùy mức độ rủi ro.

### 4.1. Language-level sandbox

Interpreter chỉ hỗ trợ một tập cú pháp và hàm được cho phép. Không có API để gọi trực tiếp reflection, filesystem hoặc process.

Ví dụ, DSL expression có thể hỗ trợ:
- Boolean và arithmetic.
- String manipulation.
- Date operations.
- Collection operations.
- Một số domain function thuần.

Ưu điểm là đơn giản và có thể kiểm soát chặt semantics. Giới hạn là nếu runtime hoặc native extension có lỗi, language-level restriction có thể bị vượt qua.

### 4.2. API-level sandbox

Host chỉ cung cấp facade hoặc capability object với các method cụ thể. Chương trình không nhận service locator hoặc container có thể truy cập mọi service.

Ví dụ, capability đọc order có thể chỉ cho phép lấy order hiện tại:

~~~text
orderAccess.currentOrder()
orderAccess.getItemSummary(itemId)
~~~

Không cung cấp một database connection tổng quát.

### 4.3. Process isolation

Chạy DSL trong process riêng tạo address space riêng và giúp supervisor có thể terminate process khi timeout hoặc crash.

Tuy nhiên, process riêng vẫn có thể truy cập tài nguyên hệ điều hành theo quyền user của nó. Cần thêm OS permission, filesystem restriction, network policy và resource limit.

### 4.4. Container isolation

Container có thể giới hạn:
- Filesystem mount.
- User và group.
- CPU và memory.
- Process count.
- Network namespace.
- Linux capabilities.
- Syscall qua seccomp.
- Writable path.

Container cần được cấu hình an toàn. Tránh chạy privileged, mount Docker socket hoặc chia sẻ thư mục host nhạy cảm.

### 4.5. Virtual machine

VM cung cấp ranh giới kernel riêng và mức cô lập mạnh hơn process/container trong một số threat model. Chi phí khởi động và tài nguyên thường cao hơn. VM có thể phù hợp với code không tin cậy hoặc workload cần isolation mạnh.

### 4.6. WebAssembly

WebAssembly (Wasm) cung cấp mô hình module và import/export rõ ràng. Module chỉ truy cập host function được import và runtime có thể giới hạn memory, execution fuel hoặc thời gian.

Wasm là lựa chọn đáng cân nhắc cho DSL được biên dịch thành module, nhưng host import vẫn là quyền thực tế của chương trình. Nếu host cung cấp API quá rộng, sandbox vẫn yếu.

### 4.7. So sánh mức cô lập

| Cơ chế | Cô lập chính | Ưu điểm | Giới hạn cần lưu ý |
| --- | --- | --- | --- |
| Interpreter giới hạn | Ngôn ngữ và API | Nhẹ, semantics rõ | Lỗi runtime hoặc extension có thể vượt ranh giới |
| Process riêng | Address space và lifecycle | Dễ terminate, crash isolation | Chưa tự giới hạn OS access |
| Container | Process và namespace OS | Quota và filesystem/network policy | Dùng chung kernel host |
| WebAssembly runtime | Module và import capability | API hẹp, memory isolation | Host import vẫn là trusted boundary |
| Virtual machine | Guest OS | Cô lập mạnh hơn trong nhiều mô hình | Tốn tài nguyên, vận hành phức tạp |

### 4.8. Defense in depth

Một hệ thống có thể kết hợp:
- Parser giới hạn kích thước và độ sâu.
- Interpreter chỉ có built-in an toàn.
- Capability API hẹp.
- Worker process riêng.
- Container không privileged.
- Network deny-by-default.
- CPU, memory và wall-clock quota.
- Supervisor có quyền terminate.
- Audit và alert.

Nhiều lớp giúp giảm khả năng một lỗi đơn lẻ làm mất toàn bộ ranh giới.

## 5. Capability-based security

Capability là quyền cụ thể được cấp cho một execution để thực hiện một thao tác trên một tài nguyên. Thay vì chương trình tự tìm mọi service có sẵn, runtime truyền vào đúng những capability cần thiết.

### 5.1. Quyền theo khả năng

Một chương trình có thể nhận:
- ReadOrderCapability cho một order ID.
- WriteResultCapability cho một output record.
- SendNotificationCapability cho một template cụ thể.
- ReadReferenceDataCapability cho một dataset đã lọc.

Chương trình không nhận quyền đọc toàn bộ database hoặc gửi mọi loại message.

### 5.2. Least privilege

Nguyên tắc least privilege yêu cầu mỗi execution chỉ có quyền tối thiểu cần thiết để hoàn thành nhiệm vụ.

Ví dụ, rule xác định discount chỉ cần đọc total, customer tier và promotion flags. Nó không cần đọc email, địa chỉ nhà hoặc payment token.

### 5.3. Capability object

Một capability object có thể đóng gói:
- Resource scope.
- Allowed operation.
- Tenant identity.
- Expiration.
- Quota.
- Audit context.

Ví dụ:

~~~text
ReadOrderCapability {
  tenantId: "tenant-17"
  orderId: "order-42"
  operations: [readSummary, readItems]
  expiresAt: ...
}
~~~

Các giá trị trong ví dụ chỉ minh họa. Capability thực tế nên được tạo ở trusted host và không thể tự giả mạo bằng dữ liệu DSL.

### 5.4. Không truyền service container

Không nên truyền toàn bộ dependency injection container, application context hoặc object graph của host vào interpreter. Một object có thể chứa reference đến nhiều service khác và làm mất ranh giới quyền.

Thay vào đó, tạo interface nhỏ và adapter kiểm tra quyền cho từng thao tác.

### 5.5. Capability attenuation

Một capability có thể được thu hẹp khi truyền cho sub-workflow hoặc function. Ví dụ, parent có quyền đọc một order; child chỉ nhận quyền đọc một số field của order đó.

Quyền con không được rộng hơn quyền cha nếu không có một trusted authority cấp thêm.

### 5.6. Thu hồi capability

Capability có thể hết hạn hoặc bị thu hồi khi:
- Execution kết thúc.
- User bị revoke quyền.
- Tenant bị khóa.
- Workflow bị cancel.
- Policy thay đổi.
- Quota bị vượt.

Runtime cần kiểm tra quyền tại thời điểm thao tác, đặc biệt với execution kéo dài.

## 6. Thiết kế API an toàn cho DSL

API host là cổng mà chương trình DSL sử dụng để tương tác với hệ thống. Thiết kế API quyết định phần lớn bề mặt tấn công.

### 6.1. API hẹp theo domain

Ưu tiên API diễn đạt thao tác nghiệp vụ cụ thể:

~~~text
inventory.reserve(orderId, itemId, quantity)
payment.request(orderId, amount, idempotencyKey)
notification.send(templateId, recipientRef)
~~~

Những API này có thể kiểm tra business rule, tenant, quota và audit. Chúng an toàn hơn API tổng quát như executeSql hoặc httpRequest không giới hạn.

### 6.2. Tránh eval và dynamic execution

Không cung cấp một hàm eval cho phép chạy mã host tùy ý. Nếu DSL cần biểu thức động, hãy parse thành AST và đánh giá bằng evaluator có semantics và whitelist rõ.

### 6.3. Tránh reflection không giới hạn

Reflection có thể cho phép truy cập method, field hoặc class không dự kiến. Chỉ expose type và member được phép. Type resolver cần dùng allowlist hoặc explicit export metadata.

### 6.4. Không expose raw host object

Một entity object host có thể có getter thực hiện lazy database load hoặc method gây side effect. Nên dùng immutable data transfer object hoặc proxy có policy rõ ràng.

### 6.5. Kiểm tra input và output

Mỗi host API cần:
- Kiểm tra kiểu.
- Kiểm tra kích thước.
- Kiểm tra tenant và ownership.
- Kiểm tra giá trị trong miền hợp lệ.
- Giới hạn số lượng phần tử.
- Chuẩn hóa lỗi.
- Mask dữ liệu trong log.

Output từ host cũng cần được giới hạn trước khi trả về sandbox.

### 6.6. Async API

Nếu DSL gọi API bất đồng bộ, runtime cần giới hạn số lời gọi đồng thời, timeout và cancellation. Không để một chương trình tạo hàng triệu future hoặc task.

### 6.7. Idempotency

Action có side effect nên hỗ trợ idempotency key hoặc request identity. Khi runtime retry sau timeout, cùng một action không nên tạo nhiều giao dịch ngoài ý muốn.

## 7. Filesystem sandbox

Filesystem là một nguồn rủi ro lớn vì host có thể chứa source, secret, credential và dữ liệu của nhiều ứng dụng.

### 7.1. Deny by default

Mặc định không cấp filesystem access cho DSL. Nếu nhiệm vụ cần đọc file, chỉ cấp một tập resource hoặc thư mục cụ thể.

### 7.2. Read-only input

Một sandbox có thể mount input ở chế độ read-only và cấp một output directory riêng. Điều này giảm nguy cơ chương trình ghi đè source hoặc file hệ thống.

### 7.3. Path traversal

Không chỉ kiểm tra chuỗi đường dẫn bắt đầu bằng một prefix. Các đường dẫn chứa segment parent, symbolic link hoặc encoding khác nhau có thể thoát khỏi thư mục dự kiến.

Cần:
- Chuẩn hóa path theo filesystem.
- Resolve symbolic link theo policy.
- Dùng directory handle hoặc API có khả năng bảo đảm root boundary.
- Kiểm tra quyền tại thời điểm mở file.
- Tránh race giữa validate path và sử dụng path.

### 7.4. Symlink và mount

Một file bên trong sandbox có thể là symlink trỏ ra ngoài. Container có thể vô tình mount thư mục host nhạy cảm. Policy cần kiểm soát cả symlink và mount configuration.

### 7.5. Giới hạn file

Nếu được phép ghi file, cần giới hạn:
- Thư mục.
- Dung lượng tổng.
- Kích thước file.
- Số file.
- Số thao tác.
- Loại file nếu phù hợp.
- Thời gian giữ file.

### 7.6. Temporary directory

Mỗi execution nên có thư mục tạm riêng, quyền truy cập hạn chế và cleanup sau khi kết thúc. Không dùng chung thư mục tạm giữa tenant nếu có nguy cơ đoán tên hoặc đọc file của nhau.

### 7.7. File handle và cleanup

Khi timeout hoặc terminate, runtime cần đóng handle và xóa dữ liệu tạm theo policy. Cleanup phải chịu được trường hợp worker crash.

## 8. Network sandbox

Network access có thể cho phép DSL gọi dịch vụ nội bộ, cloud metadata endpoint hoặc gửi dữ liệu ra ngoài.

### 8.1. Network deny-by-default

Nếu DSL không cần network, không cấp network access. Nếu cần, chỉ cho phép endpoint và operation đã khai báo.

### 8.2. SSRF

Một DSL có hàm fetch URL có thể bị lợi dụng để gọi:
- Loopback.
- Private network.
- Cloud metadata endpoint.
- Control plane.
- Service nội bộ không dành cho người dùng.

Chỉ kiểm tra hostname ban đầu là chưa đủ vì DNS có thể thay đổi hoặc redirect dẫn đến địa chỉ khác. Cần policy kiểm tra địa chỉ sau resolve, redirect, scheme, port và egress route.

### 8.3. Allowlist endpoint

Một API network capability có thể chỉ cho phép:
- Hostname cụ thể.
- Port cụ thể.
- HTTP method cụ thể.
- Path prefix cụ thể.
- Kích thước request/response.
- Timeout và rate limit.

### 8.4. Không cho tùy ý đặt header nhạy cảm

Host nên tự quản lý authorization header và credential. DSL không nên tự đặt hoặc đọc header nội bộ nếu không có capability rõ.

### 8.5. Response size và decompression

Một endpoint có thể trả response rất lớn hoặc payload nén có tỷ lệ mở rộng cao. Cần giới hạn compressed size, decompressed size, parse depth và thời gian đọc.

### 8.6. Egress proxy

Một egress proxy có policy tập trung có thể kiểm tra destination, DNS resolution, TLS và rate. Tuy nhiên, proxy chỉ hữu ích khi sandbox không thể bỏ qua nó bằng route khác.

### 8.7. Network identity

Mỗi execution hoặc tenant có thể dùng identity riêng để policy và audit. Không dùng credential chung có quyền rộng cho mọi sandbox nếu có thể tránh.

## 9. Giới hạn CPU, memory và thời gian

Resource exhaustion có thể làm ảnh hưởng toàn bộ runtime. Giới hạn phải được thực thi bởi cơ chế đáng tin cậy bên ngoài chương trình DSL.

### 9.1. Wall-clock timeout

Wall-clock timeout giới hạn tổng thời gian thực thi. Khi hết thời gian, supervisor yêu cầu cancellation và sau grace period có thể terminate worker.

### 9.2. CPU budget

CPU budget giới hạn lượng CPU time hoặc instruction/fuel. Với interpreter, có thể đếm evaluation steps. Với Wasm, runtime có thể hỗ trợ fuel hoặc epoch interruption. Với container, cgroup có thể giới hạn CPU.

### 9.3. Memory limit

Giới hạn memory giúp ngăn collection hoặc object graph quá lớn. Cần xác định hành vi khi vượt ngưỡng: trả resource-limit error, terminate execution hoặc chuyển instance sang trạng thái failed.

### 9.4. Recursion và call depth

Giới hạn:
- Call stack depth.
- AST evaluation depth.
- Recursion count.
- Nested query depth.
- Expression complexity.

Một parser có thể từ chối cấu trúc lồng quá sâu trước khi runtime chạy.

### 9.5. Collection và output size

Giới hạn số phần tử, kích thước string, số record, nested projection depth và payload output. Một chương trình có thể chạy nhanh nhưng trả hàng gigabyte dữ liệu.

### 9.6. Concurrency quota

Giới hạn số task, async call, timer và child workflow đang hoạt động. Quota có thể áp dụng theo execution, tenant và toàn cluster.

### 9.7. Quota và fairness

Một tenant không nên chiếm hết worker. Có thể áp dụng:
- Per-tenant concurrency.
- Weighted queue.
- Rate limit.
- Fair scheduling.
- Per-tenant CPU budget.
- Burst quota.

### 9.8. Cancellation

Cancellation cần lan truyền đến interpreter, async operation và host API. Nếu code đang chạy trong native call không thể interrupt, worker process có thể cần terminate sau timeout.

## 10. Kiểm soát ngôn ngữ và AST

Một DSL có thể giảm rủi ro bằng cách giới hạn những cấu trúc được phép trong grammar và semantic model.

### 10.1. Allowlist cú pháp

Một DSL expression có thể chỉ cho phép:
- Literal.
- Biến đã bind.
- Arithmetic và Boolean operators.
- Conditional expression.
- Function được export.
- Collection operators.

Không cần cung cấp import tùy ý, class loading, native call hoặc process execution nếu mục tiêu nghiệp vụ không yêu cầu.

### 10.2. AST validation

Sau parse, validator có thể duyệt AST và từ chối node không được phép trong sandbox profile.

Ví dụ, profile Formula có thể cấm:
- Loop.
- Recursion.
- Assignment.
- Function definition.
- File operation.
- Network operation.

Profile Workflow có thể cho phép action nhưng chỉ qua capability đã khai báo.

### 10.3. Type safety

Type checker nên ngăn truy cập member không được export và truyền dữ liệu sai kiểu vào host API. Static type checking giảm một số lỗi nhưng không thay authorization hoặc runtime quota.

### 10.4. Complexity budget

Có thể tính chi phí tĩnh từ:
- Số node AST.
- Độ sâu cây.
- Số function call.
- Số nhánh.
- Số nested query.
- Kích thước literal.

Static budget không dự đoán chính xác mọi runtime cost, nhưng có thể từ chối chương trình quá phức tạp trước khi chạy.

### 10.5. Recursion policy

Nếu recursion không cần thiết, cấm hoàn toàn. Nếu cần, yêu cầu khai báo giới hạn hoặc áp dụng runtime depth limit.

### 10.6. Safe built-ins

Built-in nên có semantics thuần, thời gian chạy dự đoán được và giới hạn đầu vào. Regex, JSON parser, date formatter và collection operations đều có thể gây resource exhaustion nếu không giới hạn.

### 10.7. Compile-time và runtime policy

Compile-time validator kiểm tra cấu trúc, kiểu và capability được khai báo. Runtime enforcement vẫn cần kiểm tra quyền, quota và trạng thái hiện tại vì context có thể thay đổi sau khi compile.

## 11. Cô lập dữ liệu và multi-tenancy

Một nền tảng DSL multi-tenant phải bảo vệ dữ liệu giữa các tenant ở mọi lớp.

### 11.1. Tenant context đáng tin cậy

Tenant identity phải được lấy từ authenticated execution context do host tạo. Không tin tenantId do DSL source hoặc input payload tự khai báo.

### 11.2. Scoped data access

Repository hoặc data service nhận tenant scope từ trusted context:

~~~text
orderAccess.findById(orderId)
~~~

Service tự áp dụng tenant predicate và authorization. Không yêu cầu DSL tự thêm điều kiện tenant vào mỗi query.

### 11.3. Database isolation

Có thể dùng:
- Tenant-aware query filter.
- Row-level security.
- Schema/database riêng.
- Credential riêng.
- Connection pool theo tenant hoặc policy.

Dù chọn cách nào, cần tránh một query DSL có thể bỏ qua tenant filter.

### 11.4. Cache isolation

Cache key phải bao gồm tenant hoặc security scope khi dữ liệu phụ thuộc quyền. Không dùng cache object toàn cục có thể trả dữ liệu của tenant khác.

### 11.5. Shared worker

Nếu nhiều tenant dùng chung worker process, cần tránh mutable global state, static cache không phân scope và thread-local context bị rò rỉ giữa request.

### 11.6. Execution isolation

Với workload không tin cậy, có thể dùng worker pool theo trust tier hoặc tenant group. Tenant có rủi ro cao có thể chạy trong sandbox riêng hoặc VM riêng.

### 11.7. Noisy neighbor

Một tenant có thể tạo nhiều execution hoặc workload nặng. Per-tenant quota và fair scheduling giúp giới hạn ảnh hưởng lên các tenant khác.

## 12. Secret và credential

Secret không nên xuất hiện trong DSL source, AST, debug view hoặc telemetry nếu không cần.

### 12.1. Secret reference

Thay vì nhúng API key:

~~~text
call paymentProvider.charge(order)
~~~

Host có thể resolve credential từ secret manager theo capability đã được cấp. DSL chỉ tham chiếu integration identity.

### 12.2. Secret scope

Credential cần được giới hạn theo:
- Tenant.
- Environment.
- Service.
- Operation.
- Thời hạn.
- Resource scope.

### 12.3. Không expose secret vào expression

Nếu DSL nhận secret dưới dạng String, chương trình có thể nối nó vào output hoặc log. Có thể dùng secret handle không thể serialize hoặc chỉ cho phép truyền đến API được phê duyệt.

### 12.4. Redaction

Redaction cần áp dụng ở:
- Log.
- Trace attributes.
- Exception.
- Debugger variable view.
- Pipeline output.
- Error message.
- Support bundle.

Không dựa vào việc người viết DSL tự tránh log secret.

### 12.5. Rotation và revocation

Execution dài hạn có thể sống qua thời điểm credential rotate. Host API nên resolve credential theo policy hiện tại và có khả năng revoke capability.

## 13. Giao tiếp giữa sandbox và host

Sandbox thường cần trả kết quả hoặc yêu cầu host thực hiện thao tác. Giao tiếp cần có protocol và contract rõ.

### 13.1. Input boundary

Host nên chuẩn hóa input:
- Kiểm tra schema.
- Giới hạn kích thước.
- Loại bỏ field không được phép.
- Áp dụng tenant scope.
- Đóng băng hoặc snapshot dữ liệu nếu cần tính tái lập.

### 13.2. Output boundary

Output cần được kiểm tra:
- Schema và kiểu.
- Kích thước.
- Số phần tử.
- Encoding.
- Field được phép.
- Không chứa handle hoặc object host nội bộ.

### 13.3. Host call protocol

Một request có thể có:
- Capability ID.
- Operation name.
- Input payload.
- Request ID.
- Deadline.
- Correlation ID.

Host xác minh capability, quota và quyền rồi mới thực hiện.

### 13.4. Error mapping

Host exception không nên truyền nguyên stack hoặc credential vào sandbox. Chuyển thành error code và thông điệp có cấu trúc. Diagnostic chi tiết hơn có thể chỉ dành cho operator được phân quyền.

### 13.5. Re-entrancy

Nếu host call gọi ngược vào sandbox hoặc trigger một execution khác, cần tránh re-entrant call làm phá state hoặc tạo deadlock. Có thể dùng message queue hoặc async boundary rõ ràng.

### 13.6. Protocol versioning

Khi host API thay đổi, sandbox artifact có thể đã được compile theo version cũ. Gắn API version hoặc capability version vào artifact và kiểm tra tương thích khi khởi chạy.

## 14. Plugin và extension trong sandbox

Plugin có thể mở rộng DSL bằng function, type, action hoặc data provider. Đây là bề mặt tấn công quan trọng.

### 14.1. Plugin trust level

Có thể phân loại:
- Built-in do nền tảng phát hành.
- Plugin được ký và duyệt.
- Plugin nội bộ của tổ chức.
- Extension do tenant tự cung cấp.
- Code hoàn toàn không tin cậy.

Mỗi loại có thể được phép chạy trong isolation profile khác nhau.

### 14.2. Extension contract

Plugin cần khai báo:
- Function hoặc action được export.
- Input/output schema.
- Capability yêu cầu.
- Resource quota.
- Version tương thích.
- Side effect.
- Cancellation behavior.

### 14.3. Không chạy plugin tùy ý trong host process

Nếu plugin là code native hoặc host-language code không tin cậy, chạy trong cùng process với application có thể phá ranh giới sandbox DSL. Nên dùng process hoặc runtime isolation riêng.

### 14.4. Signature và provenance

Kiểm tra nguồn phân phối, chữ ký hoặc checksum nếu nền tảng hỗ trợ. Ghi plugin version vào execution record để có thể truy nguyên.

### 14.5. Plugin dependency

Pin dependency version và kiểm tra dependency graph. Tránh tải dependency động từ nguồn không được kiểm soát trong lúc sandbox đang chạy.

### 14.6. Revocation

Nếu plugin bị phát hiện có lỗi bảo mật, hệ thống cần có cách ngăn execution mới, thu hồi capability và xác định instance nào đã dùng plugin đó.

## 15. Determinism và reproducibility

Một số DSL cần kết quả có thể tái lập, ví dụ rule engine, pricing, compliance và workflow quyết định.

### 15.1. Nguồn không xác định

Kết quả có thể phụ thuộc:
- Current time.
- Random number.
- Network response.
- Database state.
- Locale.
- Timezone.
- Environment variable.
- Thứ tự iteration không ổn định.

### 15.2. Explicit input

Đưa clock, random seed và dữ liệu ngoài vào execution context thay vì để chương trình truy cập global host state.

~~~text
executionContext {
  now: fixedInstant
  randomSeed: 48291
  locale: "vi-VN"
  timezone: "Asia/Ho_Chi_Minh"
}
~~~

### 15.3. Pure function

Pure function trả kết quả chỉ dựa trên input và không có side effect. Chúng dễ sandbox, cache và test hơn.

### 15.4. Record external result

Nếu action gọi API bên ngoài, có thể lưu request identity và response metadata để audit hoặc replay. Replay không được gọi lại side effect nếu mục tiêu là tái dựng kết quả lịch sử.

### 15.5. Deterministic execution không thay security

Một chương trình deterministic vẫn có thể truy cập dữ liệu trái phép nếu capability quá rộng. Reproducibility và security là hai mục tiêu riêng.

## 16. Lifecycle và supervisor

Sandbox execution cần được quản lý bởi một thành phần đáng tin cậy ở bên ngoài chương trình.

### 16.1. Lifecycle

Một execution có thể đi qua:

~~~text
CREATED
   |
   v
POLICY_CHECK
   |
   v
STARTING
   |
   v
RUNNING
   |
   +--> SUCCEEDED
   +--> FAILED
   +--> TIMED_OUT
   +--> CANCELLED
   +--> RESOURCE_LIMIT
~~~

### 16.2. Supervisor

Supervisor chịu trách nhiệm:
- Tạo worker hoặc runtime instance.
- Cấp input và capability.
- Áp dụng quota.
- Theo dõi heartbeat.
- Nhận kết quả.
- Hủy hoặc terminate execution.
- Thu thập telemetry.
- Cleanup resource.
- Lưu trạng thái và audit.

### 16.3. Watchdog

Watchdog có thể phát hiện worker không phản hồi, heartbeat mất hoặc execution vượt deadline. Nó cần phân biệt worker chậm với worker đã chết.

### 16.4. Graceful cancellation

Trước khi terminate cưỡng bức, supervisor có thể gửi cancellation signal và cho một khoảng grace period để cleanup. Sau đó terminate process hoặc runtime nếu không phản hồi.

### 16.5. Worker recycling

Worker có thể được tái sử dụng để giảm chi phí khởi động. Nhưng cần reset toàn bộ state giữa execution, xóa temporary data và đảm bảo không có object, thread hoặc cache của tenant trước rò sang tenant sau.

### 16.6. Crash recovery

Nếu worker crash, supervisor lưu outcome và quyết định retry theo policy. Không retry side effect một cách mù quáng. Dùng idempotency và reconciliation.

## 17. Observability và audit trong sandbox

Sandbox cần có telemetry đủ để phát hiện abuse và điều tra sự cố, nhưng không làm lộ dữ liệu.

### 17.1. Execution record

Một record có thể gồm:
- Execution ID.
- Tenant ID hoặc scoped tenant reference.
- DSL artifact version.
- Sandbox profile.
- Runtime version.
- Start/end time.
- Outcome.
- CPU và memory usage.
- Capability calls.
- Resource-limit events.
- Error code.

### 17.2. Security event

Có thể ghi:
- Capability denied.
- Path access denied.
- Network destination blocked.
- Quota exceeded.
- Invalid host call.
- Worker terminated.
- Policy version changed.
- Plugin rejected.

### 17.3. Audit trail

Audit record nên bất biến hoặc được bảo vệ chống sửa đổi theo yêu cầu hệ thống. Nó giúp biết ai tạo execution, policy nào được áp dụng và thao tác nào đã được chấp nhận.

### 17.4. Không log payload tùy tiện

Log toàn bộ DSL input hoặc host response có thể làm lộ dữ liệu. Ghi metadata, ID và error code cần thiết; nội dung nhạy cảm phải được mask hoặc loại bỏ.

### 17.5. Alert

Cảnh báo có thể dựa trên:
- Tỷ lệ capability denied tăng bất thường.
- Tenant liên tục vượt CPU quota.
- Số lần worker crash.
- Network deny event tăng.
- Nhiều execution timeout.
- Attempt truy cập resource ngoài scope.

Một lần deny có thể là lỗi cấu hình bình thường; alert nên xét tần suất, mức độ và context.

## 18. Các sandbox profile theo loại DSL

Không phải mọi DSL cần cùng một mức quyền. Có thể định nghĩa profile theo use case.

### 18.1. Formula profile

Dùng cho công thức hoặc biểu thức:
- Chỉ arithmetic, Boolean, string và date operations.
- Không có filesystem.
- Không có network.
- Không có process.
- Không có mutation.
- Giới hạn AST size, depth và evaluation fuel.
- Output là scalar hoặc record nhỏ.

### 18.2. Query profile

Dùng cho DSL truy vấn:
- Chỉ đọc qua query capability.
- Tenant scope bắt buộc.
- Allowlist entity và field.
- Giới hạn row count, query duration và nested depth.
- Không cho arbitrary SQL hoặc raw connection.
- Mask field nhạy cảm.

### 18.3. Workflow profile

Dùng cho workflow:
- Cho phép action qua registry.
- Capability theo action và instance.
- Timeout, retry và concurrency quota.
- Idempotency cho side effect.
- Event correlation.
- State persistence.
- Không có host API tổng quát.

### 18.4. Template profile

Dùng cho template hoặc document generation:
- Chỉ đọc dữ liệu đã cấp.
- Không truy cập filesystem ngoài output area.
- Không gọi network tùy ý.
- Giới hạn output size và render time.
- Escape nội dung theo output context để tránh injection.

### 18.5. Plugin profile

Dùng cho extension:
- Capability khai báo trước.
- Version pinning.
- Process hoặc Wasm isolation tùy trust.
- Resource quota.
- Signature/provenance.
- Audit và revocation.

### 18.6. Profile composition

Một execution có thể kết hợp profile nhưng quyền cuối cùng phải là giao của các policy cho phép, trừ khi một trusted authority chủ động cấp thêm. Không cộng dồn quyền một cách vô tình.

## 19. Ví dụ: sandbox cho DSL tính giá vận chuyển

Giả sử nền tảng cho phép mỗi cửa hàng viết rule tính phí vận chuyển:

~~~text
rule shippingFee(order: Order): Decimal {
  let base = 20000
  let distanceFee = order.distanceKm * 1500

  if order.total >= 1000000 {
    return 0
  }

  return base + distanceFee
}
~~~

Rule chỉ cần đọc một số trường của Order và trả về Decimal.

### 19.1. Input contract

Host tạo input DTO bất biến:

~~~text
ShippingInput {
  orderId: OrderId
  total: Decimal
  distanceKm: Decimal
  destinationZone: ZoneCode
}
~~~

Không truyền toàn bộ Order entity có thể chứa customer email, payment token hoặc lazy service reference.

### 19.2. Language profile

Cho phép:
- Variable declaration.
- Decimal arithmetic.
- Comparison.
- If expression.
- Return.
- Một số built-in thuần.

Cấm:
- Network call.
- File access.
- Reflection.
- Dynamic class loading.
- Process execution.
- Arbitrary recursion.

### 19.3. Resource policy

Ví dụ policy:
- Wall-clock timeout ngắn.
- Giới hạn evaluation steps.
- Giới hạn AST node count.
- Giới hạn output size.
- Không có async task.
- Không có filesystem hoặc network capability.

Giá trị quota cụ thể cần được hiệu chỉnh theo runtime và tải thực tế.

### 19.4. Execution flow

~~~text
Trusted Host
    |
    +--> Validate input
    +--> Resolve tenant rule version
    +--> Create sandbox context
             |
             v
        Parse / Validate
             |
             v
        Evaluate Rule
             |
             v
        Check Output Type
             |
             v
        Return Decimal
~~~

### 19.5. Kiểm tra kết quả

Host xác minh output là Decimal hợp lệ, nằm trong miền phí được phép và không phải NaN hoặc giá trị vượt giới hạn. Dù rule được type-check, host vẫn kiểm tra contract ở boundary.

### 19.6. Điều tra execution

Nếu rule timeout, execution record lưu rule version, runtime version, AST complexity, elapsed time và quota outcome. Không cần ghi toàn bộ dữ liệu khách hàng vào log.

## 20. Ví dụ: sandbox cho DSL workflow có action

Một workflow DSL có thể được phép gọi một số action nghiệp vụ:

~~~text
workflow confirmOrder(orderId) {
  let order = orderAccess.getSummary(orderId)

  if order.status != PENDING {
    reject("Order is not pending")
  }

  let reservation = inventory.reserve(
    order.id,
    order.items
  )

  payment.request(
    order.id,
    order.total,
    reservation.idempotencyKey
  )

  wait for payment.accepted
}
~~~

### 20.1. Capability registry

Runtime chỉ cung cấp:
- orderAccess.getSummary.
- inventory.reserve.
- payment.request.
- Event subscription payment.accepted.

Không cung cấp raw database, arbitrary HTTP client hoặc filesystem.

### 20.2. Capability scope

orderAccess chỉ đọc order thuộc tenant hiện tại. inventory.reserve chỉ được gọi cho kho và item được cấp. payment.request chỉ nhận amount hợp lệ và idempotency key.

### 20.3. Action policy

Mỗi action có:
- Timeout.
- Retry policy.
- Idempotency.
- Input/output schema.
- Audit event.
- Permission check.
- Cancellation semantics.

### 20.4. State và recovery

Workflow state được lưu bền vững trước khi chờ payment event. Khi worker restart, supervisor khôi phục instance và subscription. Không gọi lại payment.request nếu action đã được xác nhận gửi thành công.

### 20.5. Tenant isolation

Tenant context do host gắn vào execution. DSL không thể đổi tenant bằng cách sửa orderId hoặc truyền tenantId khác.

## 21. Những lỗi thiết kế thường gặp

**Chỉ cấm một vài từ khóa nguy hiểm.** Một chương trình có thể truy cập host qua function hoặc object khác. Hãy thiết kế API và capability boundary, đồng thời kiểm soát toàn bộ đường gọi.

**Chạy code không tin cậy trong host process.** Một lỗi interpreter hoặc extension có thể ảnh hưởng ứng dụng. Hãy chọn isolation phù hợp và giảm quyền host.

**Cho sandbox dùng chung database credential.** Một query có thể vượt tenant scope. Hãy dùng data service có authorization hoặc credential và policy theo phạm vi.

**Cho phép network tùy ý.** DSL có thể truy cập metadata endpoint hoặc service nội bộ. Hãy deny-by-default và kiểm tra destination ở egress boundary.

**Kiểm tra path bằng prefix chuỗi.** Symlink và path normalization có thể thoát thư mục. Hãy dùng API filesystem an toàn và policy ở thời điểm mở file.

**Không giới hạn CPU và memory.** Vòng lặp hoặc collection lớn có thể làm cạn worker. Hãy dùng quota được supervisor hoặc runtime thực thi.

**Chỉ dùng timeout ở UI.** Người dùng đóng màn hình không có nghĩa worker đã dừng. Hãy để supervisor enforce deadline và terminate execution.

**Expose toàn bộ service container.** DSL có thể lấy được API ngoài dự kiến. Hãy truyền capability hẹp theo nhiệm vụ.

**Tin tenant ID từ source hoặc input.** Chương trình có thể giả mạo tenant. Hãy lấy tenant context từ host đã xác thực.

**Cho plugin native chạy cùng process.** Plugin có thể có quyền ngang host. Hãy cách ly plugin không tin cậy và kiểm tra provenance.

**Không reset worker dùng chung.** State hoặc cache của execution trước có thể rò sang execution sau. Hãy cleanup và test worker reuse.

**Không kiểm tra output.** Output có thể quá lớn hoặc vi phạm contract. Hãy validate schema, kích thước và miền giá trị tại boundary.

**Log toàn bộ dữ liệu để debug.** Telemetry có thể làm lộ secret và dữ liệu cá nhân. Hãy mask, giảm dữ liệu và phân quyền.

**Cho phép sửa state hoặc database trực tiếp.** Chương trình có thể bỏ qua transition và invariant. Hãy đi qua domain API có kiểm soát.

## 22. Kiểm thử sandbox

Sandbox cần được kiểm thử như một ranh giới bảo mật. Kiểm thử chức năng thông thường không đủ để chứng minh khả năng cô lập.

### 22.1. Policy tests

Kiểm tra:
- Capability được cấp hoạt động đúng.
- Capability không được cấp bị từ chối.
- Capability hết hạn bị từ chối.
- Tenant scope không thể thay đổi.
- Operation vượt quota bị chặn.
- Policy version được ghi vào execution.

### 22.2. Language escape tests

Thử:
- Reflection.
- Dynamic import.
- Native call.
- Class loading.
- Access đến host object.
- Recursive call quá sâu.
- AST quá lớn.
- Parser nesting quá sâu.

Mục tiêu là xác nhận các đường truy cập ngoài allowlist bị từ chối.

### 22.3. Filesystem tests

Thử:
- Path traversal.
- Symlink escape.
- Read file ngoài root.
- Ghi file ngoài output directory.
- File quá lớn.
- Tạo quá nhiều file.
- Cleanup sau timeout.

### 22.4. Network tests

Thử:
- Loopback.
- Private IP.
- Cloud metadata endpoint.
- DNS rebinding scenario.
- Redirect đến địa chỉ bị cấm.
- Port không được phép.
- Response quá lớn.
- Timeout và slow response.

Các bài kiểm thử cần chạy trong môi trường cô lập, không truy cập hệ thống production.

### 22.5. Resource exhaustion tests

Tạo workload:
- Infinite loop.
- Recursion sâu.
- Regex tốn kém.
- Collection lớn.
- String lớn.
- Nhiều async task.
- Nested query.
- Output quá lớn.

Xác minh quota dừng execution và worker vẫn phục vụ workload khác.

### 22.6. Isolation tests

Chạy hai tenant đồng thời và xác minh:
- Không đọc chéo dữ liệu.
- Không chia sẻ mutable state.
- Không đọc file tạm của nhau.
- Không dùng nhầm credential.
- Không ảnh hưởng quota lẫn nhau ngoài policy.

### 22.7. Supervisor tests

Kiểm tra:
- Worker crash.
- Timeout.
- Cancellation.
- Heartbeat mất.
- Process terminate.
- Cleanup sau crash.
- Retry có idempotency.
- Worker reuse không rò state.

### 22.8. Fuzzing

Fuzz parser, AST validator, protocol decoder và host-call boundary với input sai định dạng hoặc cấu trúc cực đoan. Theo dõi crash, hang, memory growth và lỗi vượt policy.

### 22.9. Penetration testing

Với sandbox chạy code không tin cậy, cần đánh giá bảo mật độc lập theo threat model thực tế. Đặc biệt kiểm tra cấu hình container/VM, syscall boundary, network egress và host API.

## 23. Quy trình xây dựng sandbox cho DSL

Có thể triển khai theo các bước:

### Bước 1: Xác định trust level

Phân loại nguồn DSL, plugin, tenant và môi trường chạy. Xác định tài sản và hậu quả nếu chương trình vượt quyền.

### Bước 2: Chọn language subset

Chỉ hỗ trợ cú pháp cần thiết cho nhiệm vụ. Tắt hoặc loại bỏ dynamic execution, reflection và native access nếu không cần.

### Bước 3: Thiết kế capability API

Liệt kê thao tác nghiệp vụ được phép. Mỗi API có scope, schema, quota, timeout, audit và cancellation behavior.

### Bước 4: Xây policy engine

Định nghĩa profile theo loại DSL, tenant, environment và trust level. Policy cần version và được ghi vào execution record.

### Bước 5: Chọn isolation mechanism

Chọn interpreter boundary, process, container, Wasm hoặc VM dựa trên threat model. Không giả định một lớp duy nhất đủ cho mọi rủi ro.

### Bước 6: Enforce resource quota

Giới hạn CPU, memory, wall-clock, recursion, AST size, output size, file, network và concurrency.

### Bước 7: Bảo vệ data boundary

Dùng DTO, tenant-aware service, field-level authorization, redaction và output validation. Không truyền raw host object hoặc secret.

### Bước 8: Xây supervisor

Quản lý lifecycle, heartbeat, cancellation, termination, cleanup, crash recovery và worker recycling.

### Bước 9: Instrument và audit

Ghi execution identity, policy, capability call, denied operation, quota event và outcome. Giới hạn dữ liệu nhạy cảm trong telemetry.

### Bước 10: Kiểm thử tấn công và vận hành

Thực hiện policy test, escape test, resource exhaustion, network/filesystem test, multi-tenant isolation, fuzzing và penetration testing.

## 24. Kết luận

Sandbox là môi trường thực thi có giới hạn, giúp DSL chỉ sử dụng những tài nguyên và hành động được cấp. Một thiết kế an toàn cần bắt đầu từ threat model và trust boundary, sau đó kết hợp language restriction, capability-based API, isolation ở process hoặc runtime, quota tài nguyên, kiểm soát filesystem/network và bảo vệ dữ liệu tenant.

Capability hẹp giúp chương trình chỉ thực hiện đúng nhiệm vụ. Supervisor đảm bảo timeout, cancellation, termination và cleanup. Policy cần được thực thi ở runtime và host service, không chỉ ở parser hoặc giao diện. Với workload rủi ro cao, có thể kết hợp container, WebAssembly hoặc VM cùng các biện pháp OS-level phù hợp.

Sandbox không thể thay thế mọi lớp bảo mật của hệ thống. Nó cần được kiểm thử bằng các tình huống escape, resource exhaustion, path traversal, SSRF, concurrency và multi-tenant isolation. Khi ranh giới quyền rõ ràng, quota được enforce và mọi execution có thể được quan sát, nền tảng DSL có thể cho phép người dùng mở rộng hành vi mà vẫn kiểm soát được tác động lên hệ thống.

