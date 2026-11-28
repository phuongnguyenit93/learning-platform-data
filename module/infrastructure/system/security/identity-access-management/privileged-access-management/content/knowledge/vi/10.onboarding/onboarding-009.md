# Kiểm tra kết nối sau onboarding

## Mục tiêu bài học

Trong chương **Onboarding** của **Privileged Access Management (PAM)**, kiểm tra kết nối là bước xác minh rằng danh tính được phép có thể đi qua đúng luồng kiểm soát để thực hiện đúng nhiệm vụ trên hệ thống đích.

Phạm vi gồm tài khoản quản trị, tài khoản dịch vụ và những đường truy cập đến hạ tầng nhạy cảm. Việc kiểm tra cần gắn với kiểm kê quyền, least privilege, JIT/JEA, vault, luân chuyển credential, giám sát phiên và bằng chứng phục vụ kiểm toán, ứng phó sự cố.

**Mở được cổng mạng hoặc đăng nhập thành công chưa đủ để nghiệm thu onboarding.** Cần biết đã kết nối đến đâu, bằng danh tính nào, theo chính sách nào, sử dụng credential hoặc phiên bản nào và có thực hiện đúng tác vụ được phép hay không.

Sau bài học, bạn có thể:

- Phân tách kết nối thành các lớp để xác minh và chẩn đoán.
- Lập ma trận kiểm tra cho người vận hành, workload và thành phần quản lý credential.
- Phân biệt kết nối mới với phiên hoặc cache có sẵn.
- Xác minh cả tác vụ được phép và giới hạn truy cập mong muốn.
- Kiểm tra tác động của rotation, hết hạn và thu hồi theo cơ chế hệ thống.
- Ghi kết quả và bằng chứng đủ để quyết định nghiệm thu hoặc tiếp tục xử lý.

## 1. “Kết nối thành công” cần được định nghĩa cụ thể

Một hệ thống PAM có thể có nhiều đường kết nối độc lập:

| Đường | Mục tiêu cần xác minh |
| --- | --- |
| Người dùng đến cổng PAM | Xác thực danh tính và tiếp nhận yêu cầu đúng |
| Cổng PAM đến nguồn danh tính | Đánh giá điều kiện xác thực và thông tin danh tính |
| Broker đến vault | Được lấy hoặc sử dụng đúng credential cho phiên |
| Broker đến hệ thống đích | Thiết lập phiên đúng giao thức, tài khoản và tài nguyên |
| Workload đến dịch vụ bí mật | Xác thực workload và lấy đúng bí mật trong phạm vi |
| Workload đến hệ thống đích | Dùng cơ chế mới để thực hiện chức năng hợp lệ |
| Bộ rotation đến hệ thống đích | Quản lý credential được giao và xác minh kết quả |
| Các thành phần đến nơi nhận audit | Gửi và liên kết bằng chứng cần thiết |

Thành công ở một đường không chứng minh đường khác hoạt động.

Ví dụ, quản trị viên lấy được mật khẩu từ vault rồi đăng nhập trực tiếp bằng máy cá nhân không chứng minh broker có thể mở phiên. Một lần đăng nhập từ máy cá nhân cũng không chứng minh ứng dụng ở vùng mạng khác có thể kết nối.

### Ba câu hỏi phải trả lời riêng

1. **Khả năng kết nối:** các thành phần có tiếp cận đúng nhau không?
2. **Quyền sử dụng:** danh tính và hành động có được chấp nhận theo chính sách không?
3. **Chức năng nghiệp vụ hoặc vận hành:** nhiệm vụ hợp lệ có hoàn thành với quyền được thiết kế không?

Một lần kiểm tra có thể trả lời một hoặc nhiều câu hỏi, nhưng báo cáo phải nói rõ phạm vi chứng minh.

## 2. Xác định đường đi thực tế trước khi kiểm tra

### 2.1. Đường của người vận hành

~~~mermaid
flowchart LR
    User[Người vận hành] --> Portal[Cổng PAM]
    IdP[Nguồn danh tính] --> Portal
    Portal --> Policy[Chính sách và phê duyệt]
    Policy --> Broker[Session broker]
    Broker --> Vault[Vault]
    Broker --> Target[Hệ thống đích]
    Portal --> Audit[Bằng chứng]
    Broker --> Audit
    Target --> Audit
~~~

Người dùng cần được liên kết với yêu cầu, quyết định và tài khoản tại đích. Nếu đích chỉ thấy tài khoản dùng chung, phải có cơ chế bằng chứng tương ứng để phân biệt từng phiên.

### 2.2. Đường của workload

~~~text
Danh tính workload
       |
       v
Cơ chế xác thực và chính sách lấy bí mật
       |
       v
Credential được phân phối theo thiết kế
       |
       v
Ứng dụng hoặc job kết nối đến hệ thống đích
       |
       v
Tác vụ hợp lệ và bằng chứng
~~~

Ứng dụng có thể kết nối trực tiếp đến đích sau khi nhận credential. Điều cần xác minh là đúng cơ chế đã được chấp nhận, không phải ép mọi luồng ứng dụng đi qua broker dành cho phiên tương tác.

### 2.3. Đường quản lý credential

Bộ rotation có danh tính, tuyến mạng và quyền khác với người dùng hoặc workload. Kiểm tra sử dụng credential thành công chưa chứng minh có thể đổi, thu hồi hoặc đối soát credential đó.

## 3. Lập hợp đồng kiểm tra

Trước khi bắt đầu, cần xác định điều gì được coi là thành công cho từng đối tượng.

Một hợp đồng kiểm tra tối thiểu gồm:

- Tài khoản, principal hoặc workload trong phạm vi.
- Hệ thống đích, môi trường và endpoint.
- Điểm xuất phát và đường truy cập bắt buộc.
- Chính sách, điều kiện và người phê duyệt nếu có.
- Tác vụ được phép cần chứng minh.
- Giới hạn hoặc hành vi bị từ chối cần xác nhận.
- Cách tạo kết nối mới và nhận diện phiên.
- Cơ chế credential, phiên bản hoặc nguồn xác thực.
- Bằng chứng mong đợi và nơi lưu được bảo vệ.
- Tiêu chí dừng, người xử lý và tác động có thể chấp nhận.

### Ví dụ một tiêu chí đủ rõ

> Workload A trong môi trường production được xác thực bằng danh tính của A, nhận credential của tài khoản runtime A, mở kết nối mới đến đúng dịch vụ dữ liệu và hoàn thành tác vụ đã chọn trong phạm vi ứng dụng A.

Tiêu chí này rõ hơn “ứng dụng kết nối được”, vì nó xác định cả danh tính, nguồn credential, kết nối mới và chức năng cần giữ.

### Đóng băng ngữ cảnh đủ để giải thích kết quả

Cần ghi phiên bản hoặc trạng thái liên quan của chính sách, mapping đích và credential. Nếu cấu hình thay đổi giữa lúc kiểm tra, kết quả trước đó có thể không còn chứng minh trạng thái mới.

Không cần dừng mọi thay đổi của tổ chức, nhưng phải nhận diện được những thay đổi có liên quan và kiểm tra lại phần bị ảnh hưởng.

## 4. Ma trận kiểm tra theo đối tượng và đường sử dụng

| Đối tượng | Đường cần kiểm tra | Tác vụ cho phép | Giới hạn cần xác nhận |
| --- | --- | --- | --- |
| Người vận hành | Cổng PAM, phê duyệt, broker, đích | Nhiệm vụ quản trị được chấp nhận | Không vào tài nguyên hoặc quyền ngoài phạm vi |
| Workload runtime | Danh tính workload, lấy bí mật, đích | Chức năng dịch vụ cần thiết | Không lấy bí mật của workload khác |
| Pipeline triển khai | Danh tính pipeline, điều kiện chạy, đích | Phát hành hoặc migration được phép | Không dùng từ luồng hoặc môi trường ngoài chính sách |
| Bộ rotation | Vault, connector, đích | Quản lý credential được giao | Không có quyền rộng ngoài nhiệm vụ |
| Đường khẩn cấp | Quy trình break-glass phù hợp | Phục hồi trong tình huống đã định nghĩa | Có trách nhiệm, bằng chứng và xử lý sau sử dụng |

Các kiểm tra phải được lựa chọn theo phạm vi onboarding. Không phải bài nào cũng cần thử mọi loại lỗi hay mọi thành phần của toàn nền tảng.

Với những kịch bản có tác động như failover hoặc ngắt một phụ thuộc, chỉ thực hiện trong điều kiện đã được chấp nhận. Có thể dùng môi trường phù hợp để xác minh thiết kế rồi xác nhận cấu hình tương ứng ở production.

## 5. Lớp 1: đúng tài nguyên, endpoint và môi trường

Trước khi chẩn đoán mật khẩu hoặc policy, cần xác nhận không kiểm tra nhầm đích.

Những thông tin cần đối chiếu:

- Tên và định danh tài nguyên.
- Môi trường thử nghiệm hoặc production.
- Tenant, miền quản lý, instance hoặc cụm.
- Tài khoản đích và nguồn xác thực.
- Endpoint logic, node và vai trò nếu có.
- Mapping giữa bản ghi PAM và hệ thống thực tế.

Hai hệ thống có thể cùng chứa một tài khoản tên “admin”. Một endpoint kiểm tra có thể trỏ sang môi trường khác nhưng vẫn chấp nhận cùng credential. Đăng nhập thành công trong trường hợp đó là kết quả gây hiểu nhầm.

### Dấu hiệu cần dừng

Nếu danh tính máy chủ, chứng thư, host key hoặc định danh tài nguyên không khớp với giá trị được chấp nhận, cần xử lý sai lệch trước khi gửi credential.

Không bỏ kiểm tra đích hoặc chấp nhận một định danh mới tùy ý chỉ để làm cho bước tiếp theo thành công.

## 6. Lớp 2: phân giải tên, tuyến mạng và giao thức

Kiểm tra từ đúng điểm xuất phát:

- Broker thực sự được chọn.
- Node connector hoặc bộ rotation.
- Môi trường chạy workload.
- Điểm truy cập của người dùng khi có liên quan.

### Những điều cần xác minh

| Thành phần | Câu hỏi |
| --- | --- |
| Phân giải tên | Tên đích được phân giải thành tài nguyên dự kiến không? |
| Tuyến mạng | Có tuyến từ đúng nguồn đến đúng đích không? |
| Cổng và giao thức | Đích có tiếp nhận đúng giao thức được thiết kế không? |
| Trung gian | Proxy, gateway hoặc cân bằng tải có tham gia không? |
| Bảo vệ đường truyền | Quan hệ tin cậy và tham số kết nối có đáp ứng chính sách không? |
| Thời gian chờ | Timeout ở từng chặng có phù hợp với cách kết nối không? |

Một kết quả mở cổng chỉ cho biết mức tiếp cận nhất định. Nó chưa chứng minh danh tính máy chủ, xác thực người dùng, quyền ở đích hoặc khả năng ghi bằng chứng.

Timeout cũng không tự chứng minh credential sai. Lỗi có thể đến từ tuyến mạng, dịch vụ không đáp ứng hoặc thành phần trung gian.

### Không mở rộng phạm vi để tìm lỗi

Chỉ kiểm tra những endpoint và giao thức được giao. Khi cần thay đổi tuyến hoặc quyền mạng, phải sửa đúng nguyên nhân; không mở truy cập rộng cho mọi nguồn như một cấu hình lâu dài.

## 7. Lớp 3: xác thực danh tính yêu cầu

### 7.1. Người vận hành

Cần xác minh:

- Đúng danh tính cá nhân, nhóm và môi trường.
- Điều kiện xác thực cần thiết được áp dụng.
- Yêu cầu được gắn với đúng người, mục đích và tài nguyên.
- Phiên hoặc ngữ cảnh đăng nhập cũ không làm bỏ qua điều kiện cần kiểm tra.

Nếu mục tiêu là xác minh một yêu cầu mới với điều kiện xác thực cụ thể, việc dùng một phiên cũ có thể không đủ. Cần tạo ngữ cảnh kiểm tra theo cơ chế được hỗ trợ và ghi rõ trạng thái sử dụng.

### 7.2. Workload

Cần kiểm tra danh tính thực tế của workload, nơi phát hành thông tin xác thực và các điều kiện tin cậy.

Một thao tác chạy bằng tài khoản quản trị viên trên cùng máy không chứng minh workload sẽ được cấp cùng quyền. Những khác biệt về môi trường, định danh tiến trình hoặc điều kiện nhận token có thể làm kết quả khác nhau.

### 7.3. Bộ phận trung gian

Broker và connector cũng phải được xác thực với vault hoặc dịch vụ liên quan. Người dùng đã đăng nhập cổng PAM thành công không có nghĩa danh tính của broker được cấp quyền lấy credential.

Không xử lý lỗi này bằng cách cấp cho broker quyền đọc toàn bộ kho.

## 8. Lớp 4: chính sách và quyết định cấp quyền

Xác thực trả lời “ai đang yêu cầu”. Phân quyền trả lời “danh tính này được làm gì trong điều kiện hiện tại”.

Cần xác nhận:

- Đúng tài nguyên và hành động được xét.
- Điều kiện môi trường, thời gian hoặc thiết bị nếu có.
- Quyền nhóm, quyền kế thừa và policy khác có ảnh hưởng.
- Luồng phê duyệt được áp dụng khi cần.
- Quyền xem bí mật và quyền khởi tạo phiên được tách đúng ý định.
- Người yêu cầu không vô tình nhận quyền quản trị chính sách.

### Kiểm tra bị từ chối phải có nguyên nhân đúng

Một danh tính thử ngoài phạm vi bị từ chối vì nguồn xác thực hỏng chưa chứng minh policy đã chặn truy cập đúng.

Cần xác định yêu cầu đã đến lớp nào và vì sao bị từ chối. Kết quả mong đợi là chính sách hạn chế đúng hành động trong một ngữ cảnh kiểm tra hợp lệ.

Nếu dùng công cụ mô phỏng hoặc đánh giá policy, cần ghi rõ đó là bằng chứng của mô hình hoặc cấu hình được đánh giá. Không coi nó tự chứng minh mọi chặng mạng và thành phần thực thi đã hoạt động.

## 9. Lớp 5: lấy đúng credential hoặc cơ chế xác thực

Một lần lấy bí mật cần xác nhận đúng bản ghi, scope và bên được nhận.

Những bằng chứng có thể dùng:

- ID bản ghi quản lý.
- ID hoặc phiên bản credential theo khả năng hệ thống.
- Danh tính người hoặc workload nhận.
- Mã yêu cầu và thời điểm.
- Kết quả kiểm tra quyền.
- Trạng thái cấp hoặc sử dụng.

Không in giá trị bí mật ra màn hình, log, ảnh chụp hoặc hồ sơ kiểm tra để chứng minh đã lấy đúng.

### Các trường hợp dễ gây hiểu nhầm

| Trường hợp | Vì sao chưa đủ |
| --- | --- |
| Người quản trị đọc được bí mật | Chưa chứng minh workload hoặc broker có quyền đúng |
| Workload còn mật khẩu trong cấu hình cũ | Có thể đang bỏ qua đường lấy bí mật mới |
| Vault trả về một bản ghi cùng tên | Có thể nhầm môi trường hoặc principal |
| Cache vẫn giữ phiên bản cũ | Chưa chứng minh cơ chế cập nhật hoạt động |
| Credential có thời hạn được cấp | Chưa chứng minh quyền ở đích và phiên hết đúng thời điểm |

Nếu nền tảng dùng danh tính liên kết, token hoặc chứng thư thay cho mật khẩu tĩnh, cần xác minh quan hệ tin cậy, phạm vi và vòng đời tương ứng. Không ép mọi mô hình về một thao tác “đọc mật khẩu”.

## 10. Lớp 6: xác thực tại đích bằng kết nối mới

Kết nối cần được thiết lập bằng đúng đường và danh tính đã chọn.

### Vì sao phải kiểm tra kết nối mới?

Một phiên đang tồn tại có thể tiếp tục hoạt động sau khi mật khẩu đã đổi hoặc quyền nhận credential đã bị thu hồi, tùy cơ chế của đích.

Connection pool cũng có thể tái sử dụng kết nối cũ. Ứng dụng vẫn trả kết quả thành công chưa chứng minh nó đã lấy và sử dụng credential mới.

Cần có cách nhận diện:

- Thời điểm và ID của kết nối mới.
- Tài khoản hoặc principal mà đích nhận.
- Endpoint thực tế.
- Phiên bản credential hoặc liên kết với lần cấp nếu hệ thống cung cấp.
- Kết quả xác thực.

Cách tạo kết nối mới phải phù hợp với ứng dụng và mức tác động. Không tự đóng hàng loạt phiên production chỉ để có một phép thử.

### Đối với broker

Cần xác nhận người dùng thực sự làm việc qua phiên được cho phép, không tự động chuyển sang đường trực tiếp khác khi broker lỗi.

Nếu dùng tài khoản chung ở đích, bằng chứng phải giữ liên kết giữa người yêu cầu và phiên tại đích.

### Đối với ứng dụng

Cần chạy từ đúng môi trường runtime và theo cách nhận credential sẽ dùng trong vận hành. Một công cụ thử thủ công là bằng chứng bổ sung, không thay thế toàn bộ kiểm tra đường ứng dụng.

## 11. Lớp 7: tác vụ hợp lệ và giới hạn least privilege

Đăng nhập được chưa chứng minh đủ quyền cho công việc; có đủ quyền cho công việc cũng chưa chứng minh không có quyền dư.

### Kiểm tra tác vụ được phép

Chọn những tác vụ đại diện cho mục tiêu onboarding:

- Người vận hành đọc thông tin chẩn đoán trong phạm vi.
- Ứng dụng thực hiện chức năng dữ liệu được giao.
- Pipeline triển khai vào đúng tài nguyên.
- Connector xác minh credential của đúng tài khoản.

Nếu công việc cần ghi dữ liệu, chỉ thử một thao tác đọc có thể chưa đủ. Cần chọn phép thử ghi phù hợp, chẳng hạn trên tài nguyên kiểm tra được chấp nhận hoặc trong môi trường đại diện.

Không dùng hành động phá hủy production để làm bằng chứng.

### Kiểm tra giới hạn

Các giới hạn cần xác nhận có thể gồm:

- Không truy xuất bí mật của dịch vụ khác.
- Không truy cập môi trường ngoài phạm vi.
- Không tự cấp role hoặc sửa policy.
- Không thực hiện hành động ngoài nhiệm vụ JEA.
- Không kích hoạt quyền JIT khi thiếu điều kiện.

Nên dùng danh tính và tài nguyên kiểm tra được kiểm soát hoặc cơ chế đánh giá quyền phù hợp. Không thử đoán credential hay truy cập ngẫu nhiên vào tài nguyên ngoài phạm vi.

### Tránh sửa lỗi bằng quyền quá rộng

Khi tác vụ hợp lệ bị từ chối, cần xác định hành động, tài nguyên và điều kiện đang thiếu. Không mặc định cấp quản trị toàn hệ thống để làm cho phép thử chuyển sang thành công.

## 12. Kiểm tra sau rotation và thay đổi vòng đời

Khi rotation thuộc phạm vi onboarding, cần xác minh từ đầu đến cuối:

1. Thao tác thay đổi được thực hiện đúng nơi có thẩm quyền.
2. Vault hoặc cơ chế cấp ghi nhận đúng trạng thái.
3. Bên phụ thuộc nhận được phiên bản phù hợp.
4. Kết nối mới sử dụng cơ chế mới thành công.
5. Tác vụ hợp lệ vẫn hoạt động.
6. Credential cũ và phiên cũ được xử lý theo mục tiêu đã định nghĩa.
7. Bằng chứng liên kết được toàn bộ thao tác.

### Không đồng nhất các thời điểm

~~~text
Hết quyền yêu cầu trong PAM
          |
          | không tự đồng nghĩa
          v
Credential ở đích hết hiệu lực
          |
          | không tự đồng nghĩa
          v
Mọi phiên đã mở đều kết thúc
~~~

Với JIT, lease hoặc checkout, cần xác định hệ thống thực thi hết hạn ở đâu. Một bản ghi đã hết thời gian không đủ nếu đích vẫn chấp nhận credential hoặc phiên đang tồn tại ngoài mục tiêu.

Nếu nền tảng có độ trễ áp dụng, tiêu chí cần ghi rõ mức bảo đảm và thời điểm phải hoàn tất theo cơ chế thực tế. Không tự đặt một ngưỡng chung cho mọi hệ thống.

### Kết quả chưa xác định

Nếu mất kết nối sau yêu cầu đổi mật khẩu, không biết đích đã đổi hay chưa thì phải giữ trạng thái cần đối soát.

Không lặp thao tác đổi liên tục để “thử lại cho chắc”. Việc này có thể làm vault, đích và ứng dụng lệch trạng thái hơn hoặc chạm cơ chế khóa tài khoản.

## 13. Kiểm tra bằng chứng và khả năng giám sát

Một yêu cầu được thực hiện thành công nhưng không có bằng chứng theo yêu cầu chưa đáp ứng tiêu chí đầy đủ.

Cần xác nhận có thể liên kết:

~~~text
Danh tính yêu cầu
      |
      v
Quyết định và phạm vi cho phép
      |
      v
Lần lấy / sử dụng credential
      |
      v
Phiên hoặc kết nối ở đích
      |
      v
Tác vụ và kết quả cần chứng minh
~~~

Những trường hữu ích gồm mã yêu cầu, ID tài nguyên, tài khoản đích, ID phiên, thời gian, kết quả và tham chiếu credential.

### Kiểm tra giới hạn của giám sát

Không mặc định mọi giao thức đều có bản ghi phiên hoặc mọi hành động đều nhìn thấy được.

Với ứng dụng dùng connection pool và tài khoản chung, log đăng nhập ở đích thường không tự phân biệt từng người dùng nghiệp vụ. Muốn kết luận đến người dùng cuối cần bằng chứng tương ứng từ lớp ứng dụng.

Bản ghi phiên hoặc log thao tác có thể chứa dữ liệu nhạy cảm. Cần kiểm tra quyền xem và cách bảo vệ thay vì phát tán toàn bộ dữ liệu vào báo cáo nghiệm thu.

### Khi audit không đến nơi

Cần phân biệt không có hoạt động, chưa nhận được log, lỗi gửi hoặc lỗi liên kết. Nếu đây là tiêu chí bắt buộc, không đánh dấu đã đạt chỉ vì kết nối vẫn hoạt động.

## 14. Chẩn đoán theo lớp và kiểm soát thay đổi

Một quy trình chẩn đoán hiệu quả bắt đầu từ điểm thất bại đã quan sát.

| Triệu chứng | Cần kiểm tra trước | Không nên kết luận ngay |
| --- | --- | --- |
| Timeout từ broker | Đúng node, DNS, tuyến, cổng, đích | Mật khẩu sai |
| Đích có định danh không khớp | Mapping, chứng thư hoặc host key được chấp nhận | Chỉ cần bỏ kiểm tra |
| Đăng nhập PAM được, mở phiên không được | Policy, broker, quyền lấy credential, kết nối đích | Tài khoản người dùng cần toàn quyền |
| Lấy bí mật thành công, đích từ chối | Đúng principal, phiên bản, nguồn xác thực, trạng thái đích | Vault chắc chắn bị lỗi |
| Đăng nhập được, tác vụ bị từ chối | Quyền hiệu lực và scope tác vụ | Cần cấp admin toàn hệ thống |
| Ứng dụng chạy, kết nối mới lỗi | Pool, cache, cấu hình nhận credential, phiên bản mới | Rotation đã thành công |
| Chỉ một vùng mạng lỗi | Điểm xuất phát, tuyến và cấu hình vùng đó | Mọi tài khoản đều lỗi |
| Có phiên nhưng thiếu audit | Đường ghi nhận, bộ nhận, mã liên kết | Không có hoạt động cần ghi |

### Thay đổi từng nguyên nhân có căn cứ

Nếu đồng thời sửa policy, mạng và credential, kết quả cuối khó giải thích. Nên ghi giả thuyết, thay đổi liên quan và phần kiểm tra lại.

Khi thay đổi có thể ảnh hưởng các tiêu chí đã đạt, cần kiểm tra lại đúng phần bị tác động. Không cần lặp toàn bộ ma trận nếu không có lý do mới.

Nếu có dấu hiệu credential bị lộ hoặc đang bị lạm dụng, chuyển sang quy trình ứng phó phù hợp thay vì tiếp tục thử nhiều lần trên cùng đường truy cập.

## 15. Ví dụ xuyên suốt: workload A kết nối cơ sở dữ liệu

### Thiết kế mong muốn

Workload A dùng danh tính riêng để lấy credential runtime A từ vault. Ứng dụng kết nối trực tiếp đến cơ sở dữ liệu A. Người vận hành dùng broker với tài khoản bảo trì riêng.

### Kết quả ban đầu

| Phép kiểm tra | Kết quả quan sát | Phạm vi chứng minh |
| --- | --- | --- |
| DBA mở phiên broker | Thành công | Đường của DBA hoạt động trong ngữ cảnh đã thử |
| Ứng dụng đang phục vụ yêu cầu | Thành công | Những kết nối hiện hữu vẫn thực hiện được tác vụ đã quan sát |
| Workload A lấy bí mật mới | Thành công | Danh tính A được cấp bản ghi đã kiểm tra |
| Ứng dụng mở kết nối mới | Thất bại | Còn lỗi trên đường xác thực mới của ứng dụng |

Không được gộp ba kết quả đầu để kết luận onboarding đã hoàn tất.

### Phân tích

Nhóm xác định ứng dụng đọc credential khi khởi động và vẫn giữ bản cũ. Pool hiện tại tạo cảm giác dịch vụ đã chuyển sang cơ chế mới.

Cách xử lý:

1. Xác nhận đúng bản ghi, principal và phiên bản.
2. Kiểm tra cấu hình nạp lại bí mật của ứng dụng.
3. Thực hiện chuyển đổi theo kế hoạch được chấp nhận.
4. Mở kết nối mới theo cách kiểm soát được.
5. Kiểm tra chức năng hợp lệ.
6. Xác nhận credential cũ và phiên cũ theo chính sách.
7. Lưu bằng chứng và cập nhật kết quả.

Không cần cấp thêm quyền database nếu nguyên nhân thực tế là ứng dụng đang dùng credential cũ.

### Kiểm tra giới hạn và audit

Dùng một danh tính thử được kiểm soát để xác nhận không nhận được bí mật A khi ngoài policy. Cần kiểm tra lý do từ chối đúng lớp, không chỉ quan sát một lỗi chung.

Đồng thời, liên kết yêu cầu lấy bí mật của A với phiên bản đã cấp và kết nối mới ở đích theo khả năng tích hợp. Nếu chưa có đủ liên kết, phải ghi giới hạn bằng chứng.

## 16. Mẫu hồ sơ kiểm tra

Hồ sơ nên mô tả kế hoạch, bằng chứng và kết quả, không chứa giá trị bí mật.

Ví dụ sau là **dữ liệu minh họa, không phải cấu hình có thể chạy của một sản phẩm**:

~~~yaml
verification:
  reference: onboarding-connection-example
  target_reference: production-service-a
  principal_reference: service-a-runtime
  owner: service-a-operations

context:
  requester: service-a-workload
  origin: approved-runtime-environment
  path: workload-to-secret-service-to-target
  policy_reference: protected-policy-version-reference

expectations:
  fresh_connection: required
  allowed_task: approved-service-a-operation
  forbidden_scope: service-b-secret
  evidence_correlation: required

credential:
  value_in_report: forbidden
  version_reference: protected-version-reference

results:
  requester_authentication: pass
  secret_authorization: pass
  target_fresh_authentication: pass
  allowed_task: pass
  forbidden_scope_check: pass
  evidence_correlation: pending

decision:
  acceptance: not-yet-complete
  remaining_action: complete-evidence-verification
~~~

Các giá trị “pass” chỉ có ý nghĩa khi có bằng chứng tương ứng. Ví dụ này vẫn chưa hoàn tất vì liên kết bằng chứng còn chờ xử lý.

Tham chiếu policy hoặc credential nên dẫn đến nơi được bảo vệ, không sao chép token, khóa hoặc toàn bộ cấu hình nhạy cảm vào báo cáo.

## 17. Phân loại kết quả và quyết định nghiệm thu

| Trạng thái | Ý nghĩa |
| --- | --- |
| PASS | Kết quả mong đợi đã được quan sát với bằng chứng trong phạm vi xác định |
| FAIL | Kết quả quan sát không đáp ứng tiêu chí |
| BLOCKED | Chưa thực hiện hoặc chưa thể kết luận do thiếu điều kiện |
| INCONCLUSIVE | Đã có quan sát nhưng bằng chứng chưa đủ để phân biệt nguyên nhân hoặc kết quả |
| NOT_APPLICABLE | Tiêu chí không áp dụng, có lý do và phạm vi được xác nhận |

Trong ma trận, “bị từ chối đúng chính sách” có thể là PASS của một phép kiểm tra giới hạn. Ngược lại, không thể thực hiện vì đích không sẵn sàng phải được ghi là chưa đủ điều kiện, không phải đã chứng minh từ chối đúng.

### Tiêu chí quyết định

Có thể nghiệm thu khi các tiêu chí bắt buộc đã đạt:

- Đúng tài nguyên, endpoint và môi trường.
- Đúng danh tính, policy và đường truy cập.
- Xác thực mới và tác vụ hợp lệ thành công.
- Giới hạn quan trọng được xác nhận theo phương pháp phù hợp.
- Vòng đời credential được kiểm tra trong phạm vi yêu cầu.
- Có bằng chứng cần thiết và người nhận bàn giao.
- Phần còn lại được nêu rõ, không bị tính thành hoàn tất.

Nếu chấp nhận một ngoại lệ, cần có chủ sở hữu, lý do, phạm vi, biện pháp bù đắp và thời hạn xem xét. Ngoại lệ không biến một tiêu chí chưa đạt thành bằng chứng rằng cơ chế đó đã hoạt động.

### Không đo hoàn tất bằng số lần đăng nhập

Mười lần đăng nhập bằng cùng một phiên hoặc từ cùng một điểm xuất phát không thay thế những đường còn chưa được kiểm tra.

Đơn vị báo cáo nên là tiêu chí, tài khoản và đường sử dụng theo ma trận. Không trộn số phiên với số tài nguyên hoặc số workload để tạo tỷ lệ hoàn thành.

## 18. Bàn giao và khi nào cần kiểm tra lại

Sau nghiệm thu, người vận hành cần biết:

- Đường truy cập và cách nhận credential được chấp nhận.
- Đầu mối xử lý lỗi theo từng lớp.
- Hành vi dự kiến khi vault, broker hoặc đích không sẵn sàng.
- Cách dùng đường khẩn cấp theo quy trình.
- Nơi xem bằng chứng và trạng thái rotation.
- Những ngoại lệ hoặc giới hạn còn tồn tại.

Cần kiểm tra lại phần liên quan khi có thay đổi:

- Endpoint, tuyến mạng, proxy hoặc vai trò cụm.
- Danh tính, nhóm, policy hoặc quan hệ tin cậy.
- Credential, nguồn xác thực hoặc cách nạp bí mật.
- Connector, broker, giao thức hoặc ứng dụng.
- Cơ chế audit và liên kết phiên.
- Khôi phục dữ liệu PAM hoặc hệ thống đích từ backup.

Sau khôi phục, dữ liệu credential trong vault có thể không còn khớp đích. Cần đối soát trước khi coi trạng thái cũ là đã được xác minh.

Khi có lỗi mới, lưu ngữ cảnh và bằng chứng đủ để người tiếp nhận tái hiện trong phạm vi được phép. Không gửi mật khẩu kèm yêu cầu hỗ trợ.

## 19. Những lỗi thường gặp

| Lỗi | Hệ quả | Hướng sửa |
| --- | --- | --- |
| Chỉ kiểm tra cổng mạng | Bỏ sót xác thực, quyền và chức năng | Kiểm tra từng lớp theo đường thực tế |
| Kiểm tra từ máy quản trị viên | Không đại diện cho broker hoặc workload | Dùng đúng điểm xuất phát |
| Dùng phiên cũ sau rotation | Hiểu nhầm credential mới đã hoạt động | Xác minh kết nối mới |
| Chỉ dùng danh tính admin | Không thấy lỗi quyền của danh tính thật | Kiểm tra bằng principal được thiết kế |
| Lấy được bí mật là báo hoàn tất | Chưa chứng minh đích chấp nhận hoặc tác vụ chạy | Xác minh đến hệ thống đích |
| Cấp quyền rộng để hết lỗi | Làm suy yếu least privilege | Xác định quyền và điều kiện còn thiếu |
| Bỏ kiểm tra định danh máy chủ | Có thể gửi credential sai đích | Xử lý quan hệ tin cậy và mapping |
| Coi mọi lỗi là bị từ chối đúng | Nhầm sự cố với thực thi policy | Kiểm tra nguyên nhân và lớp thất bại |
| Ghi bí mật vào log kiểm tra | Tạo thêm nơi lộ credential | Dùng ID, phiên bản và tham chiếu |
| Bỏ qua bằng chứng hoặc ngoại lệ | Khó nghiệm thu và điều tra | Ghi kết quả, giới hạn, chủ sở hữu và việc còn lại |

## 20. Bài tập tự đánh giá

Một nhóm đã onboard tài khoản dịch vụ vào vault. Kiểm tra từ máy DBA mở được cổng đích, lấy được mật khẩu và đăng nhập thành công. Ứng dụng vẫn chạy trên pool cũ. Một danh tính thử ngoài phạm vi bị lỗi timeout khi yêu cầu bí mật. Log phiên chưa được liên kết với yêu cầu PAM.

Hãy xác định:

1. Những phần nào đã được chứng minh và những phần nào còn chưa rõ?
2. Vì sao kết nối của DBA không đủ đại diện cho ứng dụng?
3. Timeout có chứng minh policy đã từ chối đúng không?
4. Cần kiểm tra gì sau rotation?
5. Có thể nghiệm thu khi chưa liên kết được bằng chứng bắt buộc không?

### Gợi ý phân tích

**Phạm vi:** đã có bằng chứng cho một đường thủ công từ máy DBA. Chưa đủ chứng minh đường runtime, credential mới, quyền tác vụ và vòng đời phiên.

**Ứng dụng:** có điểm xuất phát, danh tính, cấu hình lấy bí mật và pool riêng. Cần kiểm tra đúng đường và kết nối mới.

**Timeout:** chỉ cho biết yêu cầu chưa hoàn tất trong thời gian quan sát. Phải xác định lớp thất bại trước khi kết luận về policy.

**Rotation:** cần xác minh đích, phiên bản, bên phụ thuộc, kết nối mới, tác vụ hợp lệ và cách xử lý credential hoặc phiên cũ.

**Nghiệm thu:** tiêu chí bằng chứng bắt buộc còn thiếu thì chưa thể báo hoàn tất theo tiêu chí đó. Nếu có quyết định chấp nhận ngoại lệ, phải ghi rõ giới hạn và trách nhiệm.

## 21. Những điểm cần ghi nhớ

- Kiểm tra phải theo đúng tài khoản, điểm xuất phát, đường sử dụng và tài nguyên thực tế.
- Kết nối mạng, xác thực, phân quyền, chức năng và bằng chứng là những lớp cần phân biệt.
- Phiên đang tồn tại hoặc cache có thể che giấu lỗi của credential mới.
- Cần xác nhận tác vụ được phép và những giới hạn quan trọng của least privilege, JIT/JEA.
- Hết hạn trong PAM không tự chứng minh credential và phiên ở đích đã bị thu hồi.
- Một lỗi chung không chứng minh chính sách đã chặn đúng; cần biết nguyên nhân và phạm vi bằng chứng.
- Nghiệm thu dựa trên tiêu chí đã xác minh, cùng ngoại lệ và công việc còn lại được mô tả rõ.
