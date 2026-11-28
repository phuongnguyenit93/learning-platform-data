# Workload privileged identity

## Mục tiêu bài học

Trong chương **Danh tính đặc quyền**, workload privileged identity là **danh tính mà một thành phần phần mềm sử dụng để thực hiện những hành động có đặc quyền**. Thành phần đó có thể là dịch vụ, container, máy ảo, tác vụ định kỳ, bộ điều khiển hạ tầng hoặc pipeline triển khai.

Bài học này đặt danh tính workload vào phạm vi quản lý truy cập đặc quyền — **Privileged Access Management (PAM)**. Trọng tâm là kiểm kê quyền thực tế, áp dụng least privilege, giới hạn thời gian và hành động, quản lý credential, giám sát việc sử dụng quyền và giữ bằng chứng phục vụ kiểm toán, ứng phó sự cố.

Sau bài học, bạn có thể:

- Phân biệt workload, danh tính, credential và quyền được cấp.
- Nhận diện đặc quyền trực tiếp và gián tiếp của một workload.
- Giải thích luồng nhận credential ngắn hạn và những giới hạn của cơ chế đó.
- Thiết kế cách quản lý quyền cho pipeline, dịch vụ và tác vụ hạ tầng nhạy cảm.
- Xác định dữ liệu cần giữ để truy từ một hành động đặc quyền về workload và lần chạy đã thực hiện.

## 1. Workload identity không đồng nghĩa với tài khoản ít rủi ro

**Workload** là một đơn vị phần mềm thực thi công việc. **Workload identity** là danh tính được hệ thống xác thực và phân quyền cho workload đó. Khi quyền cho phép tác động đáng kể đến dữ liệu, hạ tầng hoặc cơ chế bảo vệ, danh tính này thuộc phạm vi quản lý đặc quyền.

Ví dụ:

| Workload | Nhu cầu nghiệp vụ | Khả năng mang tính đặc quyền |
| --- | --- | --- |
| Pipeline phát hành | Triển khai một phiên bản ứng dụng | Thay đổi mã đang chạy trên production |
| Job migration | Thay đổi lược đồ cơ sở dữ liệu | Tạo, sửa hoặc xóa cấu trúc dữ liệu |
| Dịch vụ sao lưu | Đọc dữ liệu để tạo bản sao lưu | Đọc lượng lớn dữ liệu nhạy cảm hoặc quản lý bản sao lưu |
| Controller hạ tầng | Đồng bộ trạng thái tài nguyên | Tạo, sửa hoặc xóa nhiều tài nguyên |
| Bộ cấp chứng thư | Phát hành chứng thư theo yêu cầu hợp lệ | Tạo phương tiện xác thực được hệ thống khác tin cậy |
| Tác vụ quản lý bí mật | Cập nhật credential cho ứng dụng | Đọc hoặc thay đổi bí mật dùng để truy cập tài nguyên khác |

Đặc quyền được xác định bằng **khả năng thực tế**, không phải tên gọi. Một danh tính chỉ có quyền đọc nhưng đọc được toàn bộ dữ liệu khách hàng vẫn có thể là danh tính đặc quyền đối với dữ liệu đó.

Cần xem cả quyền gián tiếp. Workload không có quyền sửa IAM nhưng có thể sửa mã của một tác vụ đang chạy bằng quyền quản trị vẫn có thể tạo tác động quản trị. Tương tự, quyền sửa chính sách phát hành credential có thể mạnh hơn một quyền sử dụng credential riêng lẻ.

Không phải mọi workload identity đều có đặc quyền cao. Mục tiêu kiểm kê là nhận diện đúng phạm vi tác động, tránh vừa bỏ sót danh tính mạnh vừa áp dụng kiểm soát không phù hợp cho mọi dịch vụ.

## 2. Tách bốn khái niệm dễ bị nhầm lẫn

| Khái niệm | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| Workload và lần chạy | Thành phần thực thi và một lần thực thi cụ thể | Job triển khai ứng dụng A, lần chạy 248 |
| Danh tính hoặc principal | Chủ thể được hệ thống nhận diện để phân quyền | Danh tính triển khai production của ứng dụng A |
| Credential | Bằng chứng hoặc vật mang quyền dùng khi xác thực | Token ngắn hạn, chứng thư kèm khóa riêng, API key |
| Quyền và điều kiện | Các hành động được phép trên tài nguyên, trong ngữ cảnh xác định | Cập nhật ứng dụng A ở production trong thời hạn được cấp |

Một danh tính có thể có nhiều credential còn hiệu lực. Một credential có thể được nhiều tiến trình sử dụng nếu bị chia sẻ hoặc sao chép. Vì vậy, một dòng audit mang tên danh tính dịch vụ chưa tự chứng minh chính xác tiến trình nào đã hành động.

Cũng cần phân biệt:

- **Danh tính ở nền tảng nguồn:** ví dụ danh tính của workload trong môi trường điều phối.
- **Danh tính ở hệ thống đích:** principal hoặc vai trò mà hệ thống đích dùng để quyết định quyền.
- **Quan hệ tin cậy:** quy tắc cho phép danh tính nguồn nhận hoặc sử dụng danh tính đích.

Một tài khoản dịch vụ trong một nền tảng không tự động tương đương với tài khoản dịch vụ ở nền tảng khác. Việc ánh xạ giữa chúng phải được cấu hình, giới hạn và kiểm tra.

### Một ví dụ về nhiều bản sao thực thi

Ứng dụng A có 20 bản sao đang chạy, cùng dùng một danh tính đọc dữ liệu.

- Tách danh tính A khỏi ứng dụng B giúp giới hạn phạm vi ảnh hưởng giữa hai ứng dụng.
- Cả 20 bản sao dùng chung principal có thể làm việc quy trách nhiệm đến từng bản sao khó hơn.
- Định danh phiên, thông tin runtime và log ứng dụng có thể giúp liên kết hành động với lần thực thi cụ thể.
- Liên kết đó chỉ đáng tin trong phạm vi nguồn log, runtime và cơ chế xác thực được bảo vệ.

Không nên khẳng định rằng một danh tính “thuộc về workload A” sẽ ngăn mọi tiến trình khác dùng credential của A. Cần bảo vệ credential và môi trường thực thi để duy trì ranh giới này.

## 3. Workload nhận quyền theo những cách nào?

### 3.1. Credential tĩnh được cấp trước

Ứng dụng nhận mật khẩu, khóa hoặc API key rồi dùng credential đó truy cập tài nguyên.

Cách này có thể cần thiết với hệ thống cũ, nhưng làm phát sinh những câu hỏi:

- Credential được lưu và phân phối ở đâu?
- Có bao nhiêu bản sao, ai hoặc tiến trình nào đọc được?
- Ai chịu trách nhiệm luân chuyển và thu hồi?
- Credential có tiếp tục dùng được sau khi workload đã dừng không?

Đưa credential vào vault giúp kiểm soát lưu trữ và phân phối. Tuy nhiên, cần giải quyết cả cách workload xác thực với vault; thay một bí mật đích bằng một token vault dài hạn, có quyền rộng có thể chỉ chuyển rủi ro sang vị trí khác.

### 3.2. Danh tính do nền tảng quản lý

Nền tảng có thể cung cấp danh tính cho máy ảo, dịch vụ hoặc thành phần thực thi và thay mặt workload quản lý một phần vòng đời credential.

Cơ chế này giảm việc ứng dụng tự giữ khóa dài hạn. Mức an toàn vẫn phụ thuộc vào:

- Danh tính được gắn với tài nguyên hoặc workload nào.
- Những tiến trình nào có thể yêu cầu credential trong runtime đó.
- Quyền của danh tính và phạm vi tài nguyên được phép truy cập.
- Cách bảo vệ đường cung cấp credential và môi trường thực thi.

Nếu nhiều ứng dụng không cùng mức tin cậy dùng chung một môi trường có quyền mạnh, việc dùng danh tính do nền tảng quản lý không tự tạo ra sự cô lập giữa các ứng dụng.

### 3.3. Liên kết danh tính và cấp credential ngắn hạn

Với identity federation, hệ thống đích hoặc thành phần môi giới có thể tin cậy bằng chứng danh tính do một nguồn được chấp nhận phát hành, rồi cấp credential đích có giới hạn.

Luồng khái niệm:

```text
Workload đang chạy
       |
       | Nhận bằng chứng danh tính từ nguồn được tin cậy
       v
Dịch vụ kiểm tra quan hệ tin cậy / môi giới credential
       |
       | Kiểm tra nguồn phát hành, chủ thể, đối tượng nhận,
       | thời hạn và các điều kiện được hỗ trợ
       v
Credential đích có thời hạn và phạm vi xác định
       |
       | Gọi tài nguyên theo quyền được cấp
       v
Hệ thống đích quyết định cho phép / từ chối và ghi audit
```

Luồng này không phải đặc tả của một sản phẩm cụ thể. Có hệ thống không cần bước đổi credential riêng; cơ chế xác thực và cấp quyền thực tế phụ thuộc nền tảng.

Khi đánh giá một cơ chế federation, cần xác định:

- **Issuer:** ai phát hành bằng chứng?
- **Subject:** bằng chứng đại diện cho chủ thể nào?
- **Audience:** bằng chứng được phát hành cho bên nhận nào?
- **Thời hạn:** bằng chứng và credential đích có hiệu lực đến khi nào?
- **Điều kiện tin cậy:** môi trường, workload, dự án hoặc luồng thực thi nào được chấp nhận?
- **Quyền đích:** chủ thể sau khi xác thực có thể làm gì?

Có chữ ký hợp lệ chỉ chứng minh bằng chứng được nguồn tương ứng phát hành và chưa bị sửa theo cơ chế kiểm tra. Hệ thống vẫn phải kiểm tra đầy đủ ngữ cảnh và quyết định liệu chủ thể đó có được nhận quyền hay không.

## 4. Những đường rủi ro đặc trưng của workload đặc quyền

### 4.1. Một danh tính phục vụ quá nhiều mục đích

Dùng cùng principal cho build, triển khai, migration và sao lưu khiến tập quyền thường trở thành hợp của tất cả nhu cầu.

Nếu một tác vụ ít nhạy cảm bị chiếm quyền, credential dùng chung có thể mở đường sang tác vụ mạnh hơn. Việc điều tra cũng khó xác định hành động phát sinh từ ứng dụng nào.

Một ranh giới hữu ích là **workload, môi trường và mục đích đặc quyền**. Tuy nhiên, không cần tạo danh tính mới cho mọi tiến trình một cách máy móc; mức phân tách phải đủ để thể hiện ranh giới tin cậy và hỗ trợ thu hồi độc lập.

### 4.2. Quan hệ tin cậy quá rộng

Một chính sách chấp nhận mọi workload trong một dự án hoặc mọi pipeline của một tổ chức có thể cho phép nhiều chủ thể nhận cùng vai trò mạnh.

Các điều kiện cần đủ cụ thể cho nhiệm vụ. Nếu dùng ngữ cảnh nhánh mã, môi trường hoặc workflow để quyết định quyền, phải bảo vệ cả cấu hình tạo ra ngữ cảnh đó. Một giá trị claim phù hợp không chứng minh mã đang chạy an toàn nếu người không được phép vẫn sửa được workflow hoặc môi trường liên quan.

### 4.3. Runtime bị chiếm quyền

Ngay cả khi không có bí mật dài hạn trong mã nguồn, mã độc chạy trong cùng ngữ cảnh được tin cậy có thể sử dụng quyền mà workload hợp lệ đang có.

Rủi ro có thể đến từ:

- Mã hoặc thành phần phụ thuộc bị thay đổi ngoài ý muốn.
- Runner dùng chung với tác vụ không cùng mức tin cậy.
- Quyền truy cập tài nguyên xác thực của runtime bị mở quá rộng.
- Điểm cung cấp credential có thể bị tiếp cận qua một đường truy cập không mong muốn.
- Workload bị khai thác rồi sử dụng credential hoặc phiên hiện có.

Vì vậy, bảo vệ chuỗi cung ứng phần mềm và môi trường thực thi là một phần của việc bảo vệ workload identity.

### 4.4. Quyền “được ủy quyền tiếp” bị bỏ sót

Một workload có thể không trực tiếp đọc dữ liệu nhạy cảm nhưng được phép:

- Gắn một vai trò mạnh vào tài nguyên mới.
- Thay đổi mã hoặc cấu hình của một workload có quyền cao.
- Sửa chính sách truy cập vault.
- Cấp token hoặc chứng thư cho chủ thể khác.

Các quyền này tạo đường tiếp cận đặc quyền gián tiếp. Kiểm kê chỉ tên vai trò gán trực tiếp sẽ không mô tả đủ rủi ro.

### 4.5. Hết vòng đời ứng dụng nhưng quyền vẫn còn

Khi ứng dụng được thay thế, principal, khóa, binding và chính sách tin cậy có thể bị bỏ lại. Một danh tính không còn chủ sở hữu nhưng vẫn có quyền là khoảng trống quản trị quan trọng.

Dừng container hoặc xóa một job không đồng nghĩa mọi credential đã phát hành đều mất hiệu lực. Việc thu hồi phải bao gồm những đối tượng còn tồn tại ở hệ thống nguồn và đích.

## 5. Thiết kế quyền theo nhu cầu của từng workload

### Bước 1: Mô tả nhiệm vụ bằng hành động và tài nguyên

Thay yêu cầu “pipeline cần quyền production” bằng mô tả cụ thể:

> Pipeline phát hành của ứng dụng A cần cập nhật phiên bản ứng dụng A tại môi trường production. Pipeline không cần quản lý danh tính, đọc bí mật của ứng dụng B hoặc xóa bản sao lưu.

Mô tả này giúp tách nhu cầu thực tế khỏi vai trò tiện dụng nhưng quá rộng.

### Bước 2: Kiểm tra quyền hiệu lực

Quyền hiệu lực có thể chịu tác động của vai trò trực tiếp, nhóm, kế thừa, chính sách tài nguyên, quan hệ tin cậy và điều kiện cấp quyền.

Cần kiểm tra cả:

- Những hành động được cho phép.
- Những giới hạn hoặc điều kiện thực sự được hệ thống đích áp dụng.
- Đường chuyển sang danh tính khác.
- Khả năng sửa workload hoặc chính sách có quyền mạnh hơn.

Không nên diễn giải quyền hiệu lực như phép cộng đơn giản giữa các vai trò; mỗi hệ thống có quy tắc đánh giá riêng.

### Bước 3: Tách những nhu cầu có ranh giới khác nhau

Ví dụ:

| Nhu cầu | Hướng giới hạn |
| --- | --- |
| Dịch vụ xử lý đơn hàng | Chỉ truy cập phần dữ liệu và bí mật cần cho dịch vụ |
| Pipeline triển khai | Chỉ cập nhật tài nguyên ứng dụng được giao tại môi trường xác định |
| Job migration | Quyền thay đổi lược đồ trong đợt migration đã kiểm soát, không trao mặc định cho dịch vụ phục vụ người dùng |
| Job sao lưu | Quyền đọc nguồn cần sao lưu; xem xét tách quyền ghi bản sao lưu khỏi quyền xóa hoặc thay chính sách bảo vệ |
| Controller cấp tài nguyên | Giới hạn loại tài nguyên, phạm vi quản lý và khả năng gắn danh tính mạnh |

Các dòng trên là hướng thiết kế, không phải một tập quyền có thể áp dụng nguyên trạng cho mọi nền tảng.

### Bước 4: Giới hạn cả thời gian lẫn hành động

- **JIT — Just-in-Time:** cấp hoặc cho phép nhận quyền khi tác vụ thực sự cần, với thời hạn được kiểm soát.
- **JEA — Just Enough Administration:** giới hạn khả năng quản trị vào đúng hành động cần cho nhiệm vụ.

Với workload, hai nguyên tắc này có thể được thể hiện bằng policy API, danh tính theo tác vụ, luồng phát hành có kiểm soát hoặc giao diện quản trị giới hạn. Không phải mọi nền tảng đều dùng tên tính năng JIT/JEA hoặc hỗ trợ cùng một mô hình thực thi.

Credential ngắn hạn không tự động chứng minh đã triển khai JIT đầy đủ. Nếu workload luôn có thể nhận credential mới cho một vai trò quản trị rộng, quyền thực tế vẫn có thể sẵn có liên tục.

## 6. Ví dụ thiết kế cho pipeline phát hành production

Xét ứng dụng A với hai nhóm hoạt động:

1. Build và kiểm thử thay đổi mã.
2. Phát hành một artifact đã được chấp nhận vào production.

Một hướng thiết kế:

- Tác vụ build thông thường dùng danh tính có phạm vi phù hợp với việc build.
- Tác vụ phát hành dùng danh tính riêng cho ứng dụng A và môi trường production.
- Cấu hình workflow phát hành và môi trường production được bảo vệ khỏi sửa đổi trái phép.
- Mã hoặc tác vụ không được tin cậy không được chạy trong ngữ cảnh có thể nhận danh tính phát hành.
- Artifact được định danh rõ, có bằng chứng đủ để đối chiếu với quy trình đã chấp nhận.
- Credential phát hành được nhận theo cơ chế có kiểm soát, dùng trong thời gian cần thiết.
- Hệ thống đích ghi hành động triển khai và thông tin phiên hoặc lần chạy để liên kết.

Nếu quy trình yêu cầu người phê duyệt, cần kiểm soát quyền phê duyệt và quyền sửa chính cơ chế phê duyệt. Nhãn “production” hoặc tên nhánh trong token không thay thế các bảo vệ này.

### Đặc tả chính sách ở mức ý định

Ví dụ sau là **mô tả minh họa, không phải cấu hình để nạp vào một sản phẩm**:

```yaml
workload: application-a-release
environment: production

trusted_context:
  issuer: approved-build-identity-provider
  subject: protected-release-workflow-for-application-a
  audience: production-credential-broker

target_access:
  identity: application-a-production-deployer
  resources:
    - application-a-production
  allowed_capabilities:
    - update-application-release

credential_lifecycle:
  short_lived: true
  lifetime: bounded-by-release-task-policy
  renewal: requires-a-new-accepted-identity-proof

evidence:
  correlate:
    - workflow-run-id
    - artifact-digest
    - credential-session-id
    - target-audit-event
```

Khi triển khai thật, phải chuyển ý định này thành các điều kiện mà nền tảng hỗ trợ và kiểm tra những điểm sau:

- Issuer, subject và audience có được xác minh đúng không?
- Ai sửa được workflow hoặc điều kiện được chấp nhận?
- Credential đích thực sự có phạm vi hẹp như mô tả không?
- Có đường nhận cùng vai trò qua binding hoặc principal khác không?
- Token, phiên và quyền có kết thúc theo hành vi đã dự kiến không?
- Các định danh bằng chứng có được truyền và ghi nhận đáng tin cậy không?

Không nên sao chép một cấu hình mẫu rồi coi việc cấp token thành công là bằng chứng rằng thiết kế đã giới hạn đúng quyền.

## 7. Khi nào vẫn cần vault và luân chuyển credential?

Hệ thống đích có thể chỉ hỗ trợ mật khẩu, khóa hoặc API key dài hạn. Khi đó, cần quản lý vòng đời bí mật một cách chủ động.

Một luồng quản lý có thể gồm:

1. Tạo principal và credential theo quy trình có chủ sở hữu.
2. Đặt credential trong vault, gắn chính sách chỉ workload phù hợp được lấy.
3. Xác thực workload với vault bằng cơ chế có phạm vi và thời hạn phù hợp.
4. Phân phối bí mật qua đường được kiểm soát, hạn chế lưu bản sao ngoài nhu cầu.
5. Luân chuyển credential cùng với cập nhật các bên sử dụng.
6. Xác nhận bên sử dụng đã chuyển sang credential mới.
7. Thu hồi credential cũ và kiểm tra hành vi còn phụ thuộc vào nó.

Nếu hệ thống cho phép nhiều credential đồng thời, một khoảng chuyển tiếp được kiểm soát có thể giúp giảm gián đoạn. Nếu chỉ có một credential, cần phương án thay đổi phù hợp với khả năng hệ thống và nhu cầu sẵn sàng. Không có một trình tự luân chuyển duy nhất dùng được cho mọi dịch vụ.

Những điểm dễ bỏ sót:

- Một bản sao credential có thể còn trong bộ nhớ tiến trình, file cấu hình, artifact hoặc log.
- Đổi mật khẩu không nhất thiết vô hiệu hóa phiên đã mở.
- Xóa quyền lấy bí mật từ vault không thu hồi các bản sao đã được lấy.
- Khôi phục bản sao lưu có thể đưa cấu hình credential cũ quay lại.
- Luân chuyển chỉ theo lịch không thay thế thu hồi khẩn cấp khi nghi bị lộ.

Mục tiêu là kiểm soát cả **phát hành, phân phối, sử dụng, đổi và thu hồi**, đồng thời giữ hệ thống hoạt động đúng.

## 8. Credential ngắn hạn giúp gì và chưa giải quyết điều gì?

Credential ngắn hạn giúp giảm thời gian sử dụng của một bản credential bị lộ và giảm nhu cầu phân phối bí mật dài hạn tới ứng dụng. Đây là lợi ích quan trọng, nhưng cần hiểu các giới hạn:

| Giả định dễ sai | Điều cần kiểm tra |
| --- | --- |
| “Token hết hạn nên sự cố tự kết thúc” | Workload bị chiếm có còn nhận token mới được không? Có quyền hoặc credential khác đã được tạo không? |
| “Bỏ quan hệ tin cậy là mọi token mất hiệu lực ngay” | Credential đã phát hành được hệ thống đích xác minh và thu hồi theo cơ chế nào? |
| “Token ngắn hạn luôn bị ràng buộc với đúng tiến trình” | Credential có thể bị sao chép và phát lại không? Có cơ chế ràng buộc người giữ hoặc kênh sử dụng không? |
| “Không lưu mật khẩu trong mã là không còn bí mật” | Runtime, issuer, khóa ký và đường cấp credential vẫn cần được bảo vệ |
| “Giảm thời hạn token đã đủ least privilege” | Phạm vi hành động và tài nguyên có thực sự được thu hẹp không? |

Thời hạn nên dựa trên công việc, khả năng gia hạn, hành vi thu hồi và nhu cầu vận hành. Một con số ngắn tùy ý có thể gây lỗi tác vụ mà vẫn không sửa được quan hệ tin cậy quá rộng.

## 9. Kiểm kê và phân công trách nhiệm

Một bản kiểm kê workload đặc quyền nên trả lời được các nhóm câu hỏi sau:

| Nhóm | Nội dung cần ghi nhận |
| --- | --- |
| Nhận diện | Workload, môi trường, principal nguồn và principal đích |
| Trách nhiệm | Đội sở hữu dịch vụ, người hoặc vai trò chịu trách nhiệm quyền, đầu mối khi có sự cố |
| Mục đích | Nhiệm vụ cần đặc quyền, tài nguyên và hành động cần thiết |
| Đường nhận quyền | Credential tĩnh, danh tính nền tảng, federation hoặc hình thức khác |
| Quan hệ tin cậy | Ai phát hành bằng chứng, điều kiện được chấp nhận, ai có thể sửa cấu hình |
| Phụ thuộc | Runtime, pipeline, vault, ứng dụng và hệ thống đích liên quan |
| Vòng đời | Cách tạo, đổi, gia hạn, thu hồi và loại bỏ danh tính |
| Bằng chứng | Nguồn audit, định danh liên kết, quyền xem và nơi bảo vệ bằng chứng |

Không ghi giá trị mật khẩu, token hay khóa riêng vào bảng kiểm kê. Có thể lưu định danh của bí mật hoặc credential theo cách không làm lộ chính giá trị xác thực.

Chủ sở hữu danh tính không chỉ là người từng tạo tài khoản. Vai trò này phải có trách nhiệm xác nhận nhu cầu quyền, phối hợp thay đổi, xử lý phụ thuộc và thu hồi khi workload hết vòng đời.

Quyền quản lý nền tảng cấp credential cũng cần được xem xét. Một người không trực tiếp có vai trò production nhưng có thể sửa ánh xạ workload sang vai trò đó đang nắm khả năng tác động đến đặc quyền.

## 10. Giám sát workload khác với ghi phiên quản trị của con người

Workload thường sử dụng API hoặc kết nối tự động. Ghi hình một cửa sổ terminal không mô tả đầy đủ hoạt động này.

Cần liên kết các nguồn bằng chứng phù hợp:

```text
Workload / lần chạy
        |
        v
Sự kiện xác thực hoặc cấp credential
        |
        v
Principal và phiên ở hệ thống đích
        |
        v
Hành động, tài nguyên, kết quả và thay đổi phát sinh
```

Thông tin hữu ích có thể gồm:

- Định danh workload, môi trường và phiên bản hoặc artifact.
- Mã lần chạy, phiên runtime hoặc định danh thực thi phù hợp.
- Principal yêu cầu và principal được cấp ở đích.
- Thời điểm cấp, hết hạn và định danh phiên credential.
- Tài nguyên được truy cập, hành động, kết quả cho phép hoặc từ chối.
- Thay đổi quan hệ tin cậy, chính sách quyền và cấu hình ghi audit.

Một số tín hiệu cần được xem xét theo hành vi dự kiến của workload:

- Danh tính triển khai yêu cầu quyền hoặc truy cập tài nguyên ngoài ứng dụng được giao.
- Credential được yêu cầu từ ngữ cảnh thực thi không phù hợp.
- Job định kỳ hoạt động ngoài lịch và ngữ cảnh được chấp nhận.
- Danh tính chỉ đọc dữ liệu bắt đầu sửa chính sách truy cập.
- Tần suất cấp credential hoặc lỗi xác thực thay đổi bất thường.
- Cấu hình tin cậy hoặc nguồn audit bị thay đổi trước một thao tác nhạy cảm.

Các tín hiệu trên cần ngữ cảnh để đánh giá; chúng không tự chứng minh có xâm nhập. Tác vụ khôi phục, thay đổi lịch hoặc triển khai mới cũng có thể tạo biến động hợp lệ.

Bảo vệ bằng chứng khỏi sửa hoặc xóa trái phép và giới hạn quyền xem vì log có thể chứa dữ liệu nhạy cảm. Không ghi token, mật khẩu hoặc khóa đầy đủ để thuận tiện cho việc truy vết.

## 11. Ứng phó khi nghi workload bị chiếm quyền

Giả sử một job migration chỉ được phép chạy trong một đợt phát hành, nhưng audit cho thấy nó tiếp tục sử dụng quyền ngoài đợt đó.

Một hướng xử lý có phối hợp:

1. **Xác định phạm vi ban đầu.** Làm rõ principal, workload, lần chạy, credential hoặc phiên và tài nguyên liên quan.
2. **Ngăn nhận thêm quyền.** Kiểm soát runtime hoặc luồng thực thi đáng ngờ, tạm dừng đường cấp credential hoặc thu hẹp quan hệ tin cậy phù hợp.
3. **Xử lý quyền đã phát hành.** Kiểm tra cơ chế thu hồi token, khóa, phiên và quyền ở hệ thống đích; không giả định bước 2 đã vô hiệu hóa mọi quyền đang tồn tại.
4. **Kiểm tra tác động và khả năng duy trì quyền.** Tìm thay đổi dữ liệu, cấu hình, principal, credential mới và chính sách liên quan trong phạm vi điều tra.
5. **Bảo toàn bằng chứng.** Giữ log cần thiết, liên kết các mốc thời gian và bảo vệ dữ liệu điều tra theo quy trình.
6. **Khôi phục từ ngữ cảnh được tin cậy.** Sửa nguyên nhân, khôi phục workload phù hợp, cấp lại quyền tối thiểu và xác nhận hoạt động.
7. **Xác nhận kết thúc sự cố.** Kiểm tra đường nhận quyền cũ đã bị chặn, credential liên quan đã được xử lý và các tác động cần thiết đã được khắc phục.

Thứ tự thao tác thực tế phụ thuộc mức độ khẩn cấp và nhu cầu sẵn sàng. Với dịch vụ quan trọng, cần phối hợp đội sở hữu để vừa giới hạn thiệt hại vừa duy trì khả năng phục hồi.

Đổi credential nhưng giữ nguyên runtime đã bị chiếm có thể khiến credential mới tiếp tục bị lạm dụng. Ngược lại, chỉ thay runtime mà bỏ qua credential và thay đổi đã phát sinh cũng chưa xử lý hết sự cố.

## 12. Tình huống tự đánh giá

Một hệ thống có thiết kế như sau:

- Pipeline build của nhiều ứng dụng dùng chung một danh tính.
- Danh tính này được phép triển khai toàn bộ production và đọc một kho bí mật dùng chung.
- Hệ thống đã dùng token ngắn hạn thay cho API key tĩnh.
- Mọi workflow trong dự án đều có thể yêu cầu vai trò đó.
- Log đích chỉ ghi principal chung, chưa gắn mã lần chạy.

### Phân tích

**Vấn đề đặc quyền:** quyền triển khai toàn bộ production và đọc bí mật dùng chung tạo phạm vi tác động lớn. Build của một ứng dụng không đương nhiên cần các quyền đó.

**Vấn đề quan hệ tin cậy:** mọi workflow đều có đường nhận vai trò mạnh. Cần xem ai sửa được workflow, mã và cấu hình dự án để xác định tập chủ thể thực sự có thể dùng quyền.

**Vấn đề thời gian:** token ngắn hạn hạn chế vòng đời của từng token, nhưng mọi workflow vẫn có thể xin token mới khi đáp ứng chính sách rộng hiện tại.

**Vấn đề quy trách nhiệm:** principal chung không đủ để liên kết chắc chắn một hành động với ứng dụng và lần chạy nếu thiếu bằng chứng bổ sung đáng tin cậy.

### Hướng cải thiện

- Tách build khỏi phát hành production theo ranh giới tin cậy.
- Tách danh tính và quyền theo ứng dụng, môi trường, nhiệm vụ khi cần thu hồi và giới hạn độc lập.
- Thu hẹp vai trò đích theo tài nguyên và hành động; tách quyền đọc bí mật không phục vụ triển khai.
- Giới hạn quan hệ tin cậy vào luồng phát hành được bảo vệ.
- Bảo vệ runtime và không đặt tác vụ không được tin cậy trong ngữ cảnh nhận quyền production.
- Liên kết mã lần chạy, artifact, sự kiện cấp credential và hành động ở đích.
- Xác định rõ cơ chế ngăn cấp mới và thu hồi quyền đã cấp khi xảy ra sự cố.

Không cần quay lại dùng bí mật dài hạn để sửa các vấn đề trên. Cần hoàn thiện phạm vi quyền, quan hệ tin cậy, môi trường thực thi và bằng chứng quanh cơ chế credential ngắn hạn.

## 13. Những điểm cần ghi nhớ

- Workload privileged identity là chủ thể phần mềm có khả năng thực hiện hành động nhạy cảm, trực tiếp hoặc qua đường ủy quyền.
- Phải tách workload, principal, credential, quyền và quan hệ tin cậy khi thiết kế hoặc điều tra.
- Danh tính nền tảng và federation giảm nhu cầu phân phối bí mật dài hạn, nhưng không thay thế least privilege hay bảo vệ runtime.
- JIT giới hạn thời gian có quyền; JEA giới hạn hành động. Token ngắn hạn chỉ là một thành phần của thiết kế đó.
- Với credential tĩnh, cần vault, chủ sở hữu, quản lý phụ thuộc, luân chuyển và thu hồi có kiểm chứng.
- Bằng chứng cần trả lời được: **workload nào, lần chạy nào, nhận danh tính gì, từ quan hệ tin cậy nào, đã làm gì và quyền được kết thúc ra sao**.