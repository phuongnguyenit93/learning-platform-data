# Credential checkout trong quản lý credential đặc quyền

## 1. Credential checkout là gì?

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), **credential checkout** là quy trình cho một chủ thể được xác định nhận hoặc sử dụng một credential được quản lý, trong phạm vi, điều kiện và thời gian đã được cho phép.

Checkout thường gắn với một tài khoản hoặc đối tượng credential trong vault. Hệ thống ghi nhận ai yêu cầu, tài nguyên nào được truy cập, mục đích, thời hạn và trách nhiệm kết thúc lượt sử dụng.

Credential có thể được:

- Hiển thị hoặc trả cho người dùng qua một kênh được bảo vệ.
- Cấp cho workload qua API hoặc cơ chế tích hợp.
- Sử dụng bởi gateway để mở phiên mà không đưa giá trị secret cho người yêu cầu.
- Tạo tạm thời theo yêu cầu nếu issuer hoặc hệ thống đích hỗ trợ.

Không phải sản phẩm nào cũng gọi mọi mô hình trên là checkout. Bài học tập trung vào trách nhiệm kiểm soát khi credential được cấp hoặc sử dụng cho một công việc có phạm vi.

Điểm đặc biệt của credential là có thể bị sao chép. **Check-in không chứng minh mọi bản sao đã được xóa; checkout hết hạn không tự chứng minh credential đã mất hiệu lực tại đích.** Cần có cơ chế vòng đời và bằng chứng tương ứng.

## 2. Những đối tượng cần tách rõ

| Đối tượng hoặc thao tác | Ý nghĩa | Điều không thể tự suy ra |
|---|---|---|
| Yêu cầu truy cập | Chủ thể đề nghị thực hiện công việc | Yêu cầu hợp lệ không đồng nghĩa đã được duyệt |
| Phê duyệt | Quyết định cho phép theo thẩm quyền | Chưa chứng minh điều kiện tại thời điểm cấp vẫn còn đạt |
| Quyền đủ điều kiện | Chủ thể có thể yêu cầu một loại truy cập | Chưa phải quyền sử dụng ngay |
| Reservation | Giữ chỗ trong quá trình cấp theo thiết kế | Chưa chứng minh secret đã được bàn giao |
| Checkout | Ghi nhận lượt cấp hoặc sử dụng credential | Chưa chứng minh tác vụ tại đích đã diễn ra |
| Checkout lease | Trạng thái hoặc thời hạn của lượt sử dụng tại PAM | Chưa tự thực thi thời hạn credential tại đích |
| Check-in | Yêu cầu hoặc ghi nhận kết thúc lượt sử dụng | Không chứng minh người dùng không giữ bản sao |
| Rotation | Thay credential tại đúng nguồn quản lý | Không mặc định kết thúc mọi phiên đã mở |
| Revocation | Làm mất quyền hoặc hiệu lực theo cơ chế tương ứng | Phải xác định lớp nào đã thực sự bị thu hồi |

Một hệ thống dùng cùng một từ “lease” cho nhiều chức năng dễ gây nhầm. Cần đọc ý nghĩa của lease: nó là thời hạn giữ chỗ, thời hạn checkout, thời hạn tài khoản động hay chỉ là lịch tác vụ thu hồi.

Ví dụ, PAM ghi checkout 15 phút nhưng trả mật khẩu của một tài khoản local không có thời hạn tương ứng. Sau 15 phút, PAM có thể đánh dấu lượt mượn hết hạn; mật khẩu vẫn có thể dùng được nếu chưa có hành động tại đích.

## 3. Chọn hình thức cấp theo nhu cầu

### 3.1. Tiết lộ credential cho người dùng

Người dùng nhận giá trị secret để đăng nhập hoặc thực hiện một tác vụ được phép.

Mô hình này cần thiết trong một số môi trường, nhưng làm tăng nơi có thể tồn tại bản sao: bộ nhớ client, clipboard, công cụ quản trị, dữ liệu chẩn đoán hoặc ghi chú của người dùng.

Các kiểm soát cần làm rõ:

- Ai được quyền xem hoặc xuất secret.
- Kênh nào được phép trả secret.
- Có được lưu lại hoặc dùng ở nhiều đích không.
- Khi nào phải đổi hoặc thu hồi credential.
- Cách liên kết lượt checkout với hoạt động tại đích.
- Điều gì xảy ra khi không xác định được secret đã được nhận hay chưa.

Không đưa secret vào email, ticket, tham số lệnh dễ quan sát hoặc log để làm bằng chứng đã bàn giao.

### 3.2. Sử dụng credential qua gateway

Gateway dùng credential để tạo kết nối, còn người dùng thao tác qua phiên được cho phép.

Mô hình có thể giữ secret khỏi người dùng trong luồng đó và hỗ trợ giám sát phiên. Khả năng ghi nhận lệnh, truy vấn, màn hình hoặc truyền tệp phụ thuộc giao thức và thiết kế.

Không suy ra rằng người dùng không thể tiếp cận secret từ bất kỳ nguồn nào khác. Cũng không coi gateway là bằng chứng mọi đường đăng nhập trực tiếp đã được xử lý.

### 3.3. Cấp cho workload

Workload cần được xác thực bằng danh tính riêng và được giới hạn tài nguyên, role, điều kiện cùng vòng đời phù hợp.

Một API key dùng chung cho nhiều workload làm suy yếu quy trách nhiệm dù mọi yêu cầu đều đi qua endpoint checkout.

Nếu có thể cấp credential ngắn hạn hoặc dùng danh tính liên kết phù hợp, có thể giảm phụ thuộc vào secret dài hạn. Tuy nhiên, khả năng đó cần được xác minh tại issuer, broker và đích; không phải thuộc tính mặc định của checkout.

| Hình thức | Ai có thể giữ credential rõ? | Trọng tâm kiểm soát |
|---|---|---|
| Hiển thị hoặc trả secret | Người dùng và môi trường client | Phơi lộ, bản sao, thời gian và rotation |
| Gateway dùng thay | Gateway và các thành phần liên quan | Đường phiên, quyền và giám sát |
| API cho workload | Workload hoặc agent theo mô hình | Danh tính máy, scope, cache và vòng đời |
| Cấp động | Thành phần nhận tùy thiết kế | Thời hạn thực tế, grant và thu hồi tại đích |

## 4. Kiến trúc tham chiếu

~~~mermaid
flowchart LR
    S["Người dùng hoặc workload"] -->|Danh tính và yêu cầu| P["PAM: xác thực và policy"]
    A["Quyết định phê duyệt nếu cần"] --> P
    P -->|Kiểm tra giữ chỗ và phạm vi| L["Sổ quản lý checkout"]
    P -->|Đọc hoặc tạo credential| V["Vault, broker hoặc issuer"]
    V -->|Credential theo quyết định| D["Kênh bàn giao hoặc gateway"]
    D -->|Kết quả hoặc phiên| S
    D -->|Kết nối theo mô hình| T["Hệ thống đích"]
    S -.->|Nếu được phép dùng trực tiếp| T
    L --> R["Điều phối check-in, hết hạn và thu hồi"]
    R -->|Rotation, gỡ grant hoặc xử lý phiên| T
    P --> E["Audit và giám sát"]
    R --> E
    T --> E
~~~

Sơ đồ là mô hình logic, không yêu cầu mỗi khối là một máy chủ riêng.

Các ranh giới cần xác định:

1. Chủ thể nào được yêu cầu, nhận, sử dụng hoặc quản trị credential.
2. Nguồn nào có thẩm quyền cho trạng thái tài khoản và quyền.
3. Sổ checkout bảo đảm điều gì khi nhiều yêu cầu đồng thời.
4. Thành phần nào thực thi hết hạn và thu hồi tại đích.
5. Những đường truy cập nào không đi qua PAM.
6. Những bằng chứng nào được tạo ở PAM và ở hệ thống đích.

Sổ checkout giúp điều phối và quy trách nhiệm. Nó không tự biến một tài khoản có quyền quản trị thường trực thành một tài khoản chỉ hoạt động trong thời gian checkout.

## 5. Kiểm kê trước khi bật checkout

Đối tượng credential cần được gắn với định danh và nguồn quản lý rõ ràng.

| Nhóm dữ liệu | Nội dung cần biết |
|---|---|
| Đối tượng | Credential ID, tài khoản, target ID và môi trường |
| Nguồn xác thực | Local, directory, issuer, controller hoặc nguồn khác |
| Quyền | Role, quyền hiệu lực và phạm vi hành động |
| Owner | Người chịu trách nhiệm tài khoản và dịch vụ |
| Consumer | Người dùng, ứng dụng, job hoặc công cụ đang dùng |
| Phạm vi chia sẻ | Credential có dùng ở nhiều đích hay nhiều đối tượng vault không |
| Vòng đời | Rotation, thu hồi, hết hạn và khả năng kiểm tra |
| Phiên | Kết nối có thể tồn tại bao lâu sau khi xác thực |
| Đường ngoài PAM | API, console, đăng nhập trực tiếp hoặc nguồn secret cũ |
| Phục hồi | Phương án khi cấp, check-in hoặc rotation lỗi |

Một tài khoản tập trung có thể đăng nhập nhiều thiết bị. Nếu nó được tạo thành nhiều đối tượng vault độc lập, mỗi đối tượng giữ một khóa checkout riêng có thể không bảo đảm độc quyền cho credential nền.

Cần ánh xạ checkout tới đúng đơn vị cạnh tranh: tài khoản, credential hoặc tập đối tượng mà chính sách muốn kiểm soát. Tên hiển thị giống hoặc khác nhau không đủ để xác định đơn vị đó.

Không bật cơ chế rotation sau check-in cho một tài khoản dịch vụ trước khi biết các consumer. Một lượt sử dụng của người quản trị có thể vô tình làm hỏng công cụ backup đang dùng cùng mật khẩu.

## 6. Chính sách checkout và điều kiện cấp

Một chính sách đủ rõ có thể mô tả:

~~~text
Chủ thể đã xác minh
  → đối tượng credential và tài nguyên
  → hành động được phép
  → hình thức nhận hoặc sử dụng
  → quyền hiệu lực tại đích
  → điều kiện xác thực và phê duyệt
  → giới hạn thời gian
  → quy tắc đồng thời
  → cách kết thúc và xử lý credential
  → yêu cầu bằng chứng.
~~~

### 6.1. Tách quyền xem, sử dụng và quản trị

Người được mở phiên không nhất thiết được xem mật khẩu. Người được xem metadata không nhất thiết được lấy secret. Người vận hành vault không mặc nhiên cần sử dụng credential production.

Các quyền sửa policy, bỏ khóa checkout, gia hạn và cưỡng chế check-in cũng ảnh hưởng tới truy cập đặc quyền nên cần phạm vi và bằng chứng.

### 6.2. Mục đích và ticket không tự là thẩm quyền

Một request có lý do công việc và mã thay đổi giúp tạo bối cảnh. Chúng không thay thế việc kiểm tra danh tính, quyền, target và điều kiện.

Nếu ticket là điều kiện chính sách, cần biết nguồn xác minh trạng thái và cách ràng buộc ticket với tài nguyên hoặc tác vụ. Không tin một chuỗi do client gửi chỉ vì nó có định dạng giống mã công việc.

### 6.3. Phê duyệt có phạm vi

Quyết định nên gắn với chủ thể, hành động, target, hình thức cấp, giới hạn thời gian và các điều kiện quan trọng.

Nếu người dùng đổi phạm vi sau khi được duyệt, không được tự giữ quyết định cũ cho yêu cầu rộng hơn.

Việc phê duyệt ràng buộc tới tài khoản hay một phiên bản credential cụ thể phụ thuộc chính sách. Cần xác định rõ để xử lý rotation xảy ra giữa lúc duyệt và lúc cấp.

### 6.4. Đánh giá lại trước khi bàn giao

Chủ thể có thể bị ngừng hiệu lực hoặc mất quyền sau khi được duyệt. Tài khoản đích có thể đang reconcile, nghi lộ hoặc không còn phù hợp.

Vì vậy, approved không phải giấy phép dùng vô thời hạn. Trước khi cấp và khi renew nếu có, cần kiểm tra những điều kiện mà policy yêu cầu còn hiệu lực.

## 7. Checkout độc quyền và đồng thời

### 7.1. Độc quyền ở PAM khác độc quyền tại đích

**Exclusive checkout** thường nhằm giới hạn một lượt sử dụng đang có hiệu lực trong phạm vi được quản lý. Nó có thể giảm xung đột và hỗ trợ quy trách nhiệm.

Tuy nhiên, một người đã lấy mật khẩu trước đó vẫn có thể thử dùng bản sao ngoài PAM. Một consumer khác hoặc một phiên cũ có thể tiếp tục hoạt động.

Do đó, không nói “chỉ một người có thể đăng nhập” nếu hệ thống chỉ giữ một khóa logic trong sổ checkout. Muốn có giới hạn tương ứng tại đích cần cơ chế bổ sung được hỗ trợ và xác minh.

### 7.2. Giữ chỗ phải xử lý yêu cầu đồng thời

Hai instance PAM không nên cùng kiểm tra “đang rảnh” rồi đều cấp cùng một slot độc quyền.

Cần cơ chế cập nhật nhất quán trong phạm vi sổ quản lý, như một thao tác giữ chỗ nguyên tử hoặc điều kiện phiên bản phù hợp với kiến trúc.

~~~text
Yêu cầu A và B cùng tới
  → cả hai tham chiếu cùng đơn vị cạnh tranh
  → chỉ một yêu cầu giữ được slot theo policy
  → yêu cầu còn lại chờ hoặc bị từ chối có lý do.
~~~

Một mutex chỉ nằm trong bộ nhớ của một instance chưa đủ cho nhiều instance nếu không có cơ chế phối hợp phù hợp.

### 7.3. Phân biệt thời hạn giữ chỗ và thời hạn checkout

Một reservation ngắn có thể tránh việc giữ slot vô hạn khi luồng cấp bị dừng. Nhưng giải phóng reservation không chứng minh credential chưa bị bàn giao.

Nếu lỗi xảy ra ở ranh giới trả secret, cần theo dõi khả năng secret đã phơi lộ trước khi cấp lại hoặc đổi trạng thái.

Không giữ slot vô thời hạn trong lúc chờ phê duyệt nếu thiết kế không cần điều đó. Cách lấy slot và thời điểm lấy phải phù hợp luồng nghiệp vụ và điều kiện đồng thời.

### 7.4. Thả slot không đồng nghĩa credential an toàn để cấp tiếp

Nếu policy hứa mỗi lượt dùng có credential riêng hoặc rotation sau sử dụng, slot không nên được coi là sẵn sàng chỉ vì checkout cũ đã hết hạn trên giao diện.

Cần biết rotation hoặc thu hồi đã được xác minh chưa. Nếu policy cho phép dùng lại cùng credential, giới hạn về quy trách nhiệm và bản sao vẫn phải được ghi nhận rõ.

## 8. Quản lý trạng thái theo từng trách nhiệm

Không nên dùng một trường “checked out” để thay thế mọi trạng thái liên quan.

### 8.1. Các chiều trạng thái

| Chiều | Ví dụ trạng thái | Câu hỏi cần trả lời |
|---|---|---|
| Quyết định | Chờ duyệt, từ chối, được duyệt | Yêu cầu có thẩm quyền không? |
| Lượt checkout | Giữ chỗ, đang hoạt động, hết hạn, được trả, bị thu hồi | PAM đang quản lý lượt sử dụng ra sao? |
| Bàn giao | Chưa bắt đầu, đã thử trả, được xác nhận theo cơ chế, không xác định | Secret có thể đã được cấp chưa? |
| Credential tại đích | Còn hiệu lực, mất hiệu lực, chưa xác minh | Có còn dùng để xác thực được không? |
| Rotation hoặc cleanup | Chờ, đang chạy, đã xác minh, lỗi | Biện pháp kết thúc đã thực thi chưa? |
| Phiên | Đang mở, đã đóng, không quan sát được | Hoạt động đã xác thực còn tiếp diễn không? |

Một lượt checkout có thể hết hạn trong khi credential còn dùng được và phiên vẫn mở. Đó là trạng thái cần xử lý, không phải mâu thuẫn dữ liệu có thể xóa đi bằng cách đổi nhãn.

### 8.2. Luồng logic minh họa

~~~text
Yêu cầu
  → được phép theo policy
  → giữ chỗ theo quy tắc đồng thời
  → chuẩn bị và bàn giao
  → checkout đang hoạt động
  → check-in, hết hạn hoặc thu hồi
  → xử lý credential, grant và phiên theo policy
  → xác minh kết quả kết thúc.
~~~

Các lỗi có thể xảy ra giữa mọi bước. Cần giữ được trạng thái pending hoặc unknown để tác vụ phục hồi tiếp tục đúng phạm vi.

### 8.3. Đóng lượt sử dụng và đóng cleanup

Có thể cần ghi riêng:

~~~text
Người dùng đã yêu cầu trả credential.
Checkout không được gia hạn thêm.
Rotation còn chờ xác minh.
Phiên đang được xử lý.
Đối tượng chưa sẵn sàng cho lượt cấp tiếp theo theo policy.
~~~

Không ghi “đã thu hồi hoàn toàn” nếu chỉ mới nhận check-in. Bản ghi kết thúc cần tương xứng với các kết quả đã quan sát.

## 9. Thời hạn checkout, TTL và gia hạn

### 9.1. Phân biệt các thời hạn

| Thời hạn | Ý nghĩa |
|---|---|
| Cửa sổ được phê duyệt | Khoảng yêu cầu được phép thực hiện theo quyết định |
| Reservation timeout | Khoảng giữ chỗ trước hoặc trong khi cấp |
| Checkout duration | Khoảng PAM cho phép lượt sử dụng |
| Thời hạn của credential | Khoảng credential được đích chấp nhận theo cơ chế tương ứng |
| Thời hạn token bàn giao | Khoảng có thể lấy hoặc mở phản hồi theo thiết kế |
| Thời hạn grant | Khoảng quyền được gán tại nguồn ủy quyền |
| Tuổi phiên | Khoảng kết nối đã xác thực tiếp tục tồn tại |

Token bàn giao hết hạn không làm một mật khẩu đã nhận mất hiệu lực. Checkout hết hạn cũng không tự đóng kết nối SSH, cơ sở dữ liệu hoặc giao diện quản trị.

### 9.2. Thời điểm bắt đầu phải được định nghĩa

Thời lượng checkout có thể tính từ lúc slot được cấp, lúc credential sẵn sàng hoặc một mốc được thiết kế khác.

Cần tránh trường hợp thời gian chờ phê duyệt đã tiêu hết cửa sổ nhưng hệ thống vẫn cấp secret. Mốc bắt đầu, kết thúc và giới hạn tuyệt đối phải được kiểm tra trước bàn giao.

Các quyết định thời gian cần nguồn thời gian phù hợp và cách xử lý sai lệch. Log nên giữ thời điểm đủ rõ để liên kết sự kiện, không dựa vào đồng hồ tùy ý của client.

### 9.3. Gia hạn không chỉ là sửa expires_at

Một yêu cầu gia hạn có thể cần kiểm tra lại:

- Danh tính và trạng thái chủ thể.
- Quyền đủ điều kiện.
- Cửa sổ hoặc giới hạn phê duyệt.
- Tình trạng tài khoản, credential và tài nguyên.
- Xung đột với các lượt sử dụng khác.
- Thời gian tồn tại tối đa theo policy.
- Các sự kiện nghi ngờ hoặc điều kiện thu hồi.

Nếu gia hạn vượt quyết định đã có, cần quyết định mới theo thẩm quyền. Không dùng vòng renew để biến một lượt truy cập tạm thành quyền thường trực.

### 9.4. Hết hạn cần tác vụ có thể thực thi

Cần xác định tác vụ nào chạy khi hết hạn, ai chịu trách nhiệm, cách thử lại và bằng chứng hoàn tất.

Nếu rotation hoặc gỡ grant thất bại, trạng thái checkout vẫn phải thể hiện phần xử lý còn tồn tại. Không tự kéo dài thời hạn chỉ để tránh một cảnh báo quá hạn.

## 10. Quy trình checkout tham chiếu

### Bước 1: Xác định chủ thể và yêu cầu

Xác minh danh tính người dùng hoặc workload. Phân giải target, tài khoản, action và hình thức cấp từ nguồn được quản lý.

Không nhận đường dẫn secret tùy ý rồi dùng quyền dịch vụ rộng để đọc theo yêu cầu của client.

### Bước 2: Đánh giá policy

Kiểm tra quyền, điều kiện xác thực, mục đích, thời hạn và phê duyệt nếu có. Xác nhận không có thay đổi làm quyết định cũ không còn áp dụng.

### Bước 3: Giữ slot hoặc kiểm tra đồng thời

Thực hiện theo đơn vị cạnh tranh thực tế. Kiểm tra tài khoản không đang rotation, reconcile hoặc ở trạng thái cấm cấp theo policy.

### Bước 4: Chuẩn bị credential

Đọc phiên bản phù hợp hoặc cấp credential động. Xác định thời hạn, grant và nguồn thực thi vòng đời nếu mô hình có các thành phần đó.

Nếu không xác minh được trạng thái credential, xử lý theo policy thay vì mặc định secret trong vault luôn dùng được.

### Bước 5: Lưu trạng thái và bằng chứng cần thiết

Ghi checkout ID, subject, target, policy, credential version hoặc tham chiếu, thời hạn và trạng thái bàn giao phù hợp.

Mức bền vững cần đạt trước khi cấp là một yêu cầu thiết kế. Nếu audit là điều kiện bắt buộc, phải có phương án khi không thể ghi bằng chứng. Việc trả lỗi chưa tự xử lý credential động đã được tạo.

### Bước 6: Bàn giao hoặc mở phiên

Dùng kênh được bảo vệ và xác minh đúng bên nhận hoặc máy chủ. Không log giá trị secret hoặc đưa secret vào địa chỉ URL dễ bị lưu lại.

Nếu đi qua gateway, liên kết checkout với session ID trong phạm vi cơ chế hỗ trợ.

### Bước 7: Theo dõi lượt sử dụng

Quản lý gia hạn, check-in, hết hạn và thu hồi. Nối dữ liệu với log tại đích để nhận diện hành động ngoài phạm vi hoặc việc dùng sau thời hạn.

### Bước 8: Kết thúc và xác minh

Thực hiện xử lý credential, grant và phiên theo policy. Chỉ ghi kết quả thu hồi tương ứng khi có bằng chứng tại lớp liên quan.

## 11. API, retry và bàn giao không xác định

Các cấu trúc sau là giả mã, không phải API của sản phẩm cụ thể. Định danh và thời hạn là dữ liệu minh họa.

### 11.1. Yêu cầu checkout

~~~json
{
  "request_id": "request-maintenance-042",
  "credential_object_id": "credential-db-maintenance-prod",
  "target_id": "database-production-017",
  "action": "open-approved-maintenance-session",
  "delivery_mode": "gateway",
  "requested_duration_seconds": 900,
  "purpose_reference": "change-042"
}
~~~

Thời lượng 900 giây chỉ minh họa. Policy và khả năng hệ thống quyết định giới hạn thật.

Các thuộc tính do client gửi là yêu cầu, không phải bằng chứng rằng client được phép dùng action, target hoặc delivery mode đó.

### 11.2. Metadata trả về

~~~json
{
  "checkout_id": "checkout-081",
  "subject_id": "operator-017",
  "credential_object_id": "credential-db-maintenance-prod",
  "credential_version_reference": "credential-version-12",
  "delivery_mode": "gateway",
  "lease_state": "active",
  "target_credential_expiry": "not-established-by-this-metadata",
  "session_reference": "session-081"
}
~~~

Ví dụ không trả giá trị secret. Trường lease_state không được dùng thay bằng chứng credential tại đích đã có cùng thời hạn.

### 11.3. Timeout không chứng minh chưa cấp

PAM có thể đã ghi trạng thái, tạo credential hoặc gửi phản hồi nhưng client không nhận được kết quả rõ ràng.

Cần có cách tra cứu và đối soát theo checkout ID hoặc request ID. Request ID phải được ràng buộc với danh tính, nội dung và ngữ cảnh; không được trở thành cách đọc lại kết quả của người khác.

Một ACK hoặc sự kiện gửi phản hồi có thể giúp vận hành, nhưng không chứng minh con người đã xem secret hoặc không giữ bản sao. Bằng chứng cần mô tả đúng điều được quan sát.

### 11.4. Retry không được tự cấp thêm quyền

Hệ thống cần quy định yêu cầu lặp trả trạng thái cũ, mở lại luồng hay tạo lượt mới trong điều kiện nào.

Không tự trả secret sau khi lượt checkout đã được trả hoặc thu hồi chỉ vì client dùng lại request ID cũ.

Tính lặp an toàn phải được thiết kế cho từng hành động. Một mã yêu cầu không tự làm issuer hoặc hệ thống đích hỗ trợ chống tạo trùng tài khoản.

### 11.5. Khi cấp động nhưng không bàn giao được

Có thể tồn tại tài khoản hoặc token đã tạo mà client chưa dùng. Cần theo dõi và thu hồi hoặc đối soát theo vòng đời.

Không bỏ quên đối tượng tại đích chỉ vì request trên PAM được đánh dấu failed.

## 12. Check-in và rotation sau sử dụng

### 12.1. Check-in là một tín hiệu kết thúc

Người dùng hoặc workload có thể check-in khi xong việc. Hệ thống cũng có thể kết thúc lượt theo thời gian hoặc quyết định thu hồi.

Check-in cần xác minh chủ thể được phép thực hiện và lượt đang ở trạng thái nào. Người quản trị cưỡng chế check-in phải có quyền và bằng chứng riêng.

Một lời xác nhận “đã xóa secret” không chứng minh mọi bản sao trên client, clipboard hoặc hệ thống chẩn đoán đã biến mất.

### 12.2. Rotation cần được thực thi tại đúng nguồn

Một luồng có thể là:

~~~text
Nhận tín hiệu kết thúc
  → chặn renew hoặc cấp tiếp theo policy
  → xử lý các phiên cần kết thúc
  → thay hoặc thu hồi credential ở đúng nguồn
  → cập nhật trạng thái vault
  → cập nhật consumer trong phạm vi
  → xác minh bằng cơ chế phù hợp
  → ghi kết quả cleanup.
~~~

Thứ tự cụ thể phụ thuộc nền tảng và mục tiêu. Không mặc định có một thứ tự áp dụng được cho mọi tài khoản.

Đổi mật khẩu tài khoản directory có thể ảnh hưởng nhiều đích. Thay private key trong vault không tự gỡ public key cũ. Thu hồi token cần được issuer hoặc đích thực thi theo khả năng.

### 12.3. Rotation thất bại

Nếu đích đã đổi nhưng vault chưa cập nhật, có thể phát sinh mất đồng bộ. Nếu tác vụ timeout, có thể chưa biết thay đổi đã áp dụng chưa.

Cần dừng retry thiếu kiểm soát, đối soát, dùng phương án reconcile hoặc phục hồi được cho phép và ghi trạng thái chưa hoàn tất.

Không đánh dấu credential sẵn sàng chỉ vì checkout trước đã hết hạn hoặc người dùng đã bấm trả.

### 12.4. Rotation không tự đóng phiên

Phiên đã xác thực có thể tiếp tục sau khi credential đổi. Cần xác định tác vụ kết thúc phiên hoặc giới hạn tuổi phiên khi mục tiêu yêu cầu.

Nếu người dùng đã thực hiện thay đổi bền vững như tạo khóa, tài khoản hoặc grant khác, rotation credential ban đầu không tự loại bỏ những thay đổi đó.

## 13. Tài khoản dịch vụ và consumer dùng chung

### 13.1. Không áp dụng luồng con người một cách máy móc

Một tài khoản dịch vụ có thể được dùng liên tục bởi nhiều instance. Rotation theo mỗi check-in của một người có thể làm các consumer bị lỗi.

Cần biết:

- Ai là owner dịch vụ.
- Những workload nào dùng credential.
- Consumer lấy secret lúc khởi động hay refresh được.
- Có cache hoặc connection pool không.
- Có hỗ trợ chuyển đổi credential an toàn không.
- Có thể tách tài khoản quản trị tương tác khỏi tài khoản runtime không.

Quyền checkout cho con người và quyền lấy secret cho workload nên được thiết kế theo nhu cầu riêng.

### 13.2. Credential dài hạn và ngắn hạn có hành vi khác nhau

Credential động có thể cho mỗi workload hoặc lần chạy một principal riêng, nếu nền tảng hỗ trợ. Điều đó có thể cải thiện quy trách nhiệm và thu hồi theo phạm vi.

Nhưng vẫn cần hiểu thời hạn thật, grant, phiên và khả năng thu hồi trước hạn. Một lease trong broker không tự biến thành thời hạn tài khoản tại cơ sở dữ liệu.

### 13.3. Kiểm tra sau cập nhật

Cần kiểm tra kết nối mới hoặc tác vụ đại diện, không chỉ nhìn một kết nối cũ vẫn hoạt động.

Nếu consumer giữ reference cũ trong cấu hình mong muốn, lần triển khai sau có thể tái tạo lỗi. Cần cập nhật đúng nguồn cấu hình và giữ bằng chứng theo consumer.

## 14. Thu hồi và ứng phó khi có dấu hiệu lạm dụng

Chủ thể có thể bị ngừng hiệu lực, mục đích truy cập không còn hoặc xuất hiện dấu hiệu credential bị lộ trong khi checkout còn hoạt động.

### 14.1. Xử lý theo nhiều lớp

| Lớp | Hành động có thể cần | Giới hạn cần kiểm tra |
|---|---|---|
| Danh tính | Chặn xác thực hoặc bằng chứng mới | Token đã phát hành có thể còn hiệu lực |
| Policy PAM | Chặn checkout mới và renew | Không tự thu hồi secret đã nhận |
| Lượt checkout | Đánh dấu revoked và bắt đầu cleanup | Là trạng thái quản lý, cần tác vụ thực thi |
| Credential | Rotation, vô hiệu hóa hoặc thu hồi theo cơ chế | Không phải mọi loại đều thu hồi ngay được |
| Grant | Gỡ quyền tạm hoặc role assignment | Quyền kế thừa hoặc grant khác có thể còn |
| Phiên | Đóng tại gateway hoặc đích | Cần biết các phiên ngoài đường quan sát |
| Thay đổi bền vững | Kiểm tra tài khoản, khóa, job hoặc policy mới | Thu hồi credential không tự đảo ngược hoạt động |

### 14.2. Khoảng trễ phải được nhìn thấy

Cần đo từ quyết định thu hồi tới hiệu lực ở các lớp liên quan. Nếu có độ trễ do cache hoặc cơ chế token, hồ sơ phải nêu rõ và có phương án giảm ảnh hưởng phù hợp.

Không gọi một checkbox revoked là bằng chứng toàn bộ truy cập đã bị ngăn.

### 14.3. Giữ mối liên hệ phục vụ điều tra

Checkout ID, credential version, chủ thể, target và session reference giúp xác định phạm vi.

Không dùng giá trị secret làm mã tương quan. Nếu credential bị ghi ra log trong lúc điều tra, cần xử lý sự phơi lộ đó như một phần của vòng đời credential.

## 15. Audit và bằng chứng quy trách nhiệm

### 15.1. Sự kiện cần được phân biệt

Nên lưu theo mô hình và khả năng hệ thống:

- Ai tạo yêu cầu, yêu cầu action và target nào.
- Ai quyết định, theo policy và phạm vi nào.
- Khi nào slot được giữ hoặc bị từ chối do xung đột.
- Credential version hoặc principal nào được cấp.
- Bàn giao đã được thử hay đã có xác nhận theo cơ chế nào.
- Checkout bắt đầu, gia hạn, hết hạn, được trả hoặc bị thu hồi.
- Rotation, gỡ grant và xử lý phiên có kết quả gì.
- Những điều chưa xác minh hoặc còn lỗi.

Không thu gọn tất cả thành sự kiện “user accessed password” nếu cơ chế chỉ biết đã gửi phản hồi.

### 15.2. Liên kết với hoạt động tại đích

~~~text
Danh tính đã xác minh
  → request và quyết định
  → checkout ID
  → credential version hoặc tài khoản được cấp
  → session hoặc sự kiện xác thực tại đích
  → hoạt động trong phạm vi được ghi nhận
  → check-in, hết hạn hoặc thu hồi
  → bằng chứng cleanup.
~~~

Log checkout chứng minh hành động của PAM trong phạm vi quan sát. Nếu người dùng nhận secret rồi kết nối trực tiếp, cần nguồn bổ sung để biết họ đã làm gì tại đích.

Một tài khoản dùng chung có thể gây giới hạn quy trách nhiệm. Kết hợp thời gian, tài khoản, nguồn kết nối và session reference giúp điều tra nhưng không tự bảo đảm định danh tuyệt đối cho mọi kết nối ngoài luồng.

### 15.3. Ghi trạng thái trung gian trung thực

Một bản ghi minh họa:

~~~yaml
checkout_record:
  checkout_id: checkout-081
  subject_id: operator-017
  target_id: database-production-017
  credential_reference: credential-db-maintenance-prod
  credential_version_reference: credential-version-12
  decision_policy_version: policy-v7
  lease_state: returned
  cleanup_state: rotation-pending
  credential_validity_at_target: not-yet-verified
  session_state: termination-pending
  evidence_reference: evidence-081
~~~

Đây là cấu trúc logic, không phải cấu hình sản phẩm. Nó cho thấy returned không tương đương cleaned-up hoặc target-access-revoked.

Bản ghi cần thời điểm và lịch sử thay đổi phù hợp. Không ghi đè trạng thái cũ đến mức mất khả năng tái hiện điều gì đã xảy ra.

### 15.4. Bảo vệ dữ liệu bằng chứng

Không lưu password, private key, token xác thực nguyên vẹn hoặc nội dung phản hồi secret vào audit.

Thông tin tài khoản, target và cấu trúc quyền cũng có thể nhạy cảm. Cần giới hạn quyền xem, sửa và xuất bằng chứng theo trách nhiệm.

## 16. Checkout liên quan tới least privilege, JIT và JEA thế nào?

### 16.1. Checkout không tự giảm quyền tại đích

Một credential chỉ được cấp trong vài phút nhưng có quyền toàn bộ hạ tầng vẫn có phạm vi ảnh hưởng lớn.

Least privilege cần xét quyền hiệu lực, tài nguyên, hành động và khả năng tạo quyền gián tiếp. Role được đặt tên “maintenance” không chứng minh chỉ thực hiện được bảo trì.

### 16.2. JIT cần có giới hạn được thực thi

Checkout có thể là một bước trong luồng Just-in-Time:

~~~text
Chủ thể đủ điều kiện
  → yêu cầu cho một công việc
  → quyết định có phạm vi và thời gian
  → credential hoặc grant được cấp
  → sử dụng trong điều kiện được phép
  → thu hồi và xác minh.
~~~

Nếu tài khoản vẫn có quyền thường trực và credential còn dùng ngoài PAM, chỉ giới hạn thời điểm hiển thị secret chưa tạo ra toàn bộ giới hạn JIT tại đích.

Cần chỉ ra thành phần thực thi từng giới hạn: PAM, issuer, role assignment, gateway hoặc hệ thống đích.

### 16.3. JEA cần giới hạn năng lực thực hiện công việc

Just Enough Administration hướng tới cấp đủ năng lực cho một tác vụ, chẳng hạn chẩn đoán thay vì toàn quyền thay cấu hình.

Có thể cần role tại đích, endpoint tác vụ, API có scope hoặc gateway hỗ trợ ràng buộc phù hợp. Giới hạn phải bao phủ những đường hành động liên quan, không chỉ tên role.

Ghi hình và cảnh báo hỗ trợ giám sát, nhưng không thay thế hoàn toàn việc ngăn hành động ngoài phạm vi.

## 17. Vận hành khi PAM hoặc đường thu hồi gặp lỗi

### 17.1. Phân biệt các tình huống

| Lỗi | Câu hỏi vận hành |
|---|---|
| Không xác minh được danh tính | Có đủ bằng chứng để cấp mới không? |
| Không đọc được policy hiện tại | Điều kiện độ mới và dữ liệu tin cậy là gì? |
| Không giữ được slot nhất quán | Có còn bảo đảm quy tắc đồng thời không? |
| Không truy cập được vault | Checkout mới hoặc phiên qua gateway bị ảnh hưởng ra sao? |
| Bàn giao timeout | Credential có thể đã được cấp không? |
| Rotation lỗi | Credential cũ còn hiệu lực và có thể cấp tiếp không? |
| Không tới được đích để đóng phiên | Khoảng truy cập còn tiếp diễn và phương án xử lý là gì? |
| Hệ thống audit lỗi | Có cơ chế ghi bền vững hoặc giới hạn cấp theo policy không? |

Không chuyển một điều kiện không xác minh được thành đạt chỉ để luồng tiếp tục.

### 17.2. Dữ liệu cache cần giới hạn

Nếu PAM hoặc client dùng cache, cần biết cache chứa secret, policy, trạng thái nhóm hay checkout.

Cache có thể làm giảm phụ thuộc thời điểm đọc, nhưng cũng tạo bản sao và độ trễ thu hồi. Không tự kéo dài một credential hết hạn hoặc một quyết định cũ chỉ vì nguồn hiện tại không truy cập được.

### 17.3. Không làm mất tác vụ cleanup khi tiến trình dừng

Sổ quản lý cần đủ bền vững để nhận diện checkout tới hạn và tiếp tục xử lý sau failover hoặc khởi động lại.

Một timer trong bộ nhớ không đủ nếu không có cơ chế phục hồi trạng thái. Đồng thời, nhiều worker cleanup không nên chạy chồng gây đổi credential hoặc gỡ grant sai phạm vi.

Cơ chế phối hợp phải được thiết kế theo kiến trúc triển khai, không mặc định chỉ cần nhiều instance là có tính sẵn sàng đúng.

### 17.4. Đường khẩn cấp có vòng đời riêng

Khi cần break-glass, phải có điều kiện, chủ thể, phạm vi, bằng chứng và rà soát sau sử dụng.

Không tự bỏ kiểm tra quyền hoặc cấp một mật khẩu quản trị dự phòng chung cho mọi yêu cầu khi checkout gặp lỗi.

Nếu sử dụng đường khẩn cấp làm lộ credential cho thêm chủ thể, cần xử lý vòng đời sau đó và kiểm tra khả năng hoạt động độc lập với điểm hỏng liên quan.

## 18. Tình huống xuyên suốt: một lượt bảo trì production

### 18.1. Bối cảnh

An cần thực hiện chẩn đoán trên một cơ sở dữ liệu production. Policy giả định:

- Chỉ cho role chẩn đoán đã được xác minh.
- Đi qua gateway, không xuất mật khẩu cho An.
- Cần phê duyệt trong phạm vi công việc.
- Mỗi thời điểm chỉ có một checkout trong đơn vị cạnh tranh đã xác định.
- Khi kết thúc, đóng phiên và xử lý credential theo cơ chế đã được kiểm chứng.
- Chỉ cấp lượt tiếp theo khi các điều kiện cleanup của policy đạt.

Thời lượng và cơ chế trong ví dụ là của tình huống giả định, không phải quy tắc chung cho mọi hệ thống.

### 18.2. Diễn biến

| Mốc | Sự kiện | Điều đã được chứng minh |
|---|---|---|
| 14:00 | Yêu cầu được duyệt | Có quyết định cho chủ thể, action, target và cửa sổ cụ thể |
| 14:02 | PAM đánh giá lại, giữ slot và mở phiên | Checkout cùng phiên được cấp theo điều kiện tại thời điểm đó |
| 14:12 | An yêu cầu check-in | Có tín hiệu kết thúc từ người dùng |
| 14:13 | Gateway xác nhận phiên đã đóng | Phiên được theo dõi đã kết thúc |
| 14:14 | Rotation tại nguồn và cập nhật vault được thực hiện | Có thay đổi cần xác minh kết quả |
| 14:15 | Kiểm tra vòng đời đạt trong phạm vi | Cleanup có bằng chứng theo policy và slot có thể được giải phóng |

Không dùng sự kiện 14:12 để khẳng định credential đã mất hiệu lực. Mỗi bước trong bảng xác nhận một kết quả khác nhau.

### 18.3. Một yêu cầu khác tới trong lúc cleanup

Bình yêu cầu cùng credential lúc 14:13. Theo policy của tình huống, tài nguyên chưa sẵn sàng cho lượt tiếp theo vì rotation còn chưa xác minh.

PAM cần trả trạng thái phù hợp như chờ hoặc không sẵn sàng, thay vì cấp cùng credential chỉ vì An đã check-in.

Nếu tổ chức chọn policy khác, phải hiểu ảnh hưởng của việc dùng lại credential và bằng chứng quy trách nhiệm. Không thay policy ngầm trong lúc có tải.

### 18.4. Nếu rotation timeout

Giả sử tác vụ không nhận được phản hồi sau khi yêu cầu đổi credential. Hệ thống ghi cleanup ở trạng thái chưa xác định, giữ tham chiếu phiên bản và dừng retry mù.

Đội xử lý đối soát đúng tài khoản và nguồn xác thực, xác minh hoặc reconcile theo thẩm quyền, sau đó mới xác định điều kiện cấp lượt tiếp theo.

An đã check-in và phiên gateway đã đóng là dữ kiện có ích, nhưng chưa thay thế bằng chứng rotation. Nếu có phiên ngoài gateway hoặc credential đã được xuất ở luồng khác, phạm vi xử lý phải mở theo dữ kiện đó.

### 18.5. Giới hạn cần giữ rõ

Trong luồng này, PAM không trả secret cho An. Tuy nhiên, không thể dùng điều đó để kết luận credential chưa từng bị lộ trong toàn bộ lịch sử.

Cần tiếp tục quản lý quyền xuất secret, tài khoản dịch vụ dùng chung nếu có, đường truy cập trực tiếp và credential của chính gateway.

## 19. Kiểm chứng triển khai và chỉ số quản trị

### 19.1. Tình huống cần kiểm chứng

| Tình huống | Kết quả cần quan sát |
|---|---|
| Người dùng hợp lệ nhưng không có quyền | Không được cấp chỉ nhờ xác thực thành công |
| Yêu cầu thay target sau khi duyệt | Không dùng quyết định cũ cho phạm vi rộng hơn |
| Chủ thể mất quyền trước bàn giao | Điều kiện được đánh giá lại theo policy |
| Hai yêu cầu độc quyền đồng thời | Chỉ có kết quả phù hợp quy tắc giữ slot |
| Hai đối tượng vault trỏ cùng credential nền | Không vô tình vượt quy tắc cạnh tranh |
| Retry sau timeout bàn giao | Không tạo thêm lượt hoặc trả secret trái trạng thái |
| Checkout hết hạn | Cleanup được kích hoạt, không chỉ đổi nhãn |
| Check-in nhưng rotation lỗi | Phần chưa hoàn tất còn được nhìn thấy |
| Gỡ grant hoặc đổi credential | Hành vi phiên đã mở được kiểm tra riêng |
| Failover PAM | Không mất checkout hoặc tác vụ tới hạn |
| Dùng API cho workload | Danh tính và scope được ràng buộc đúng |
| Đường khẩn cấp được dùng | Có bằng chứng và xử lý sau sử dụng |

Đây là các mục tiêu kiểm chứng hành vi. Chúng không yêu cầu thực hiện thay đổi nguy hiểm trên production để tạo bằng chứng.

### 19.2. Chỉ số có ý nghĩa

- Checkout theo chủ thể, tài nguyên và hình thức cấp.
- Tỷ lệ checkout dùng secret export so với mô hình không tiết lộ secret.
- Lượt quá hạn hoặc cleanup chưa hoàn tất.
- Thời gian từ check-in hoặc quyết định thu hồi tới hiệu lực ở đích.
- Lỗi rotation, trạng thái không xác định và thời gian đối soát.
- Yêu cầu bị từ chối do quyền, điều kiện hoặc xung đột.
- Lượt có đủ liên kết tới phiên hoặc sự kiện tại đích.
- Quyền quản trị thao tác cưỡng chế checkout hoặc bỏ khóa.
- Credential dùng chung cho nhiều mục đích.
- Ngoại lệ kéo dài và công việc khắc phục còn tồn tại.

Số lượt checkout nhiều không tự chứng minh PAM hiệu quả. Một hệ thống có thể ghi rất nhiều lượt nhưng vẫn cấp cùng credential quản trị rộng, không rotation và không quan sát được hoạt động ở đích.

## 20. Những lỗi thường gặp và bài tập áp dụng

### 20.1. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Checkout hết hạn được hiểu là password hết hiệu lực | Bản sao vẫn có thể dùng tại đích | Xác định và xác minh cơ chế hết hiệu lực |
| Check-in là coi mọi bản sao đã xóa | Đánh giá thấp phơi lộ | Quản lý rotation hoặc thu hồi theo policy |
| Slot độc quyền chỉ khóa một instance | Nhiều yêu cầu có thể cùng được cấp | Phối hợp nhất quán trong phạm vi triển khai |
| Nhiều vault object che cùng một tài khoản nền | Vượt quy tắc độc quyền | Chuẩn hóa đơn vị cạnh tranh thực tế |
| Approved được dùng vô thời hạn | Cấp khi chủ thể hoặc điều kiện đã đổi | Kiểm tra lại trước cấp và renew |
| Secret được log để chứng minh bàn giao | Tạo thêm điểm lộ | Ghi metadata và tham chiếu |
| Retry luôn tạo mới | Có lượt hoặc credential mồ côi | Ràng buộc request, đối soát và xử lý vòng đời |
| Trả slot ngay khi check-in dù policy cần rotation | Lượt tiếp theo dùng credential chưa được xử lý | Tách lease và cleanup |
| Rotation tài khoản dùng chung không biết consumer | Dịch vụ bị gián đoạn | Kiểm kê và phối hợp consumer |
| Đổi password là coi phiên đã đóng | Hoạt động cũ tiếp diễn | Quản lý phiên riêng |
| Audit checkout được coi là log toàn bộ thao tác | Bỏ sót hành động tại đích | Liên kết nguồn quan sát phù hợp |
| Bỏ kiểm soát khi PAM lỗi | Hình thành đường truy cập rộng | Quy trình lỗi và khẩn cấp có phạm vi |

### 20.2. Bài tập

Một đội cho quản trị viên checkout mật khẩu quản trị mạng trong 20 phút. Sau khi người dùng check-in, PAM lập tức giải phóng slot. Rotation chạy theo hàng đợi nhưng có thể thất bại. Công cụ backup dùng cùng mật khẩu. Mọi người vẫn có thể SSH trực tiếp từ mạng quản trị. Dashboard chỉ báo checkout đã đóng.

Hãy trả lời:

1. Thời hạn 20 phút đang giới hạn điều gì?
2. Exclusive checkout có chứng minh chỉ một người dùng tài khoản không?
3. Vì sao trạng thái đã đóng chưa đủ cho kết luận thu hồi?
4. Điều gì có thể xảy ra với công cụ backup?
5. Cần bổ sung trạng thái, bằng chứng và cơ chế nào?
6. Có thể tách nhu cầu quản trị viên và tự động hóa như thế nào?

Hướng phân tích:

- Cần kiểm tra thời hạn tại PAM có được thực thi thành hiệu lực credential hoặc phiên tại đích không.
- Sổ checkout không tự chặn bản sao credential và đường SSH trực tiếp.
- Cleanup, rotation, grant và phiên có thể chưa được xác minh dù lease đã đóng.
- Rotation có thể làm backup mất xác thực nếu consumer không cập nhật đúng.
- Cần nhìn thấy phần xử lý còn tồn tại, kiểm tra tại đúng nguồn và liên kết bằng chứng.
- Có thể phân tách tài khoản hoặc phương thức theo nhu cầu, giảm quyền, quản lý consumer và dùng đường không tiết lộ secret khi phù hợp khả năng hệ thống.

## 21. Các điểm cần nắm

Credential checkout là quy trình cấp và theo dõi việc sử dụng credential theo danh tính, phạm vi, điều kiện và thời gian. Giá trị của nó phụ thuộc cả policy, đồng thời, cách bàn giao và cơ chế kết thúc tại đích.

Check-in, hết hạn, rotation, thu hồi và đóng phiên là những hành động khác nhau. Mỗi hành động cần có trạng thái và bằng chứng tương ứng.

Khi đánh giá một luồng checkout, hãy theo một yêu cầu từ quyết định cấp tới credential, hoạt động tại đích và kết quả cleanup. Chỉ khẳng định điều hệ thống đã xác minh trong phạm vi cụ thể.
