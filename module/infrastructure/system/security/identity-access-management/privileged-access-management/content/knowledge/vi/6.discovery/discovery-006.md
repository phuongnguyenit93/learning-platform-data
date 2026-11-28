# Phát hiện service account mạnh

## Mục tiêu bài học

Trong chương **Discovery** của quản lý truy cập đặc quyền (**Privileged Access Management — PAM**), phát hiện service account mạnh là nhận diện những danh tính tự động hóa có thể thực hiện hành động nhạy cảm hoặc tạo tác động lớn trên hệ thống. Đối tượng có thể chạy ứng dụng, job định kỳ, pipeline, tác vụ sao lưu hoặc dịch vụ quản trị hạ tầng.

Từ **mạnh** ở đây mô tả khả năng và phạm vi đặc quyền của tài khoản, không mô tả độ phức tạp của mật khẩu. Một tài khoản dùng credential được bảo vệ tốt vẫn có thể giữ quyền quá rộng. Ngược lại, một danh tính chỉ có quyền hẹp vẫn cần được bảo vệ nếu credential dễ bị lấy hoặc bị dùng sai.

Sau bài học, bạn có thể:

- Xây dựng danh mục ứng viên service account từ nhiều nguồn và xác định bên sử dụng thực tế.
- Đánh giá quyền hiệu lực, đường nhận quyền gián tiếp và phạm vi tác động của từng tài khoản.
- Phân biệt quyền cần thiết, quyền dư và trường hợp chưa đủ bằng chứng.
- Ưu tiên tài khoản cần quản lý bằng least privilege, vault, credential ngắn hạn, JIT/JEA hoặc giám sát phù hợp.
- Tạo hồ sơ phát hiện có chủ sở hữu, bằng chứng và bước xử lý tiếp theo.

## 1. Service account là gì trong bài học này?

**Service account là tài khoản hoặc danh tính được dùng để một phần mềm, tác vụ hay dịch vụ truy cập tài nguyên.** Nó có thể là tài khoản trong directory, tài khoản cục bộ, tài khoản cơ sở dữ liệu hoặc một loại danh tính workload do nền tảng cung cấp.

Không phải mọi nền tảng đều dùng cùng tên gọi. Service principal, managed identity và service account của hệ thống điều phối có mô hình kỹ thuật khác nhau. Khi đưa vào danh mục PAM, cần lưu đúng loại danh tính và cơ chế phân quyền, thay vì coi chúng là những tài khoản mật khẩu giống nhau.

Cũng có trường hợp tự động hóa chạy bằng tài khoản người dùng thông thường. Nếu chỉ tìm tên có tiền tố `svc-`, discovery sẽ bỏ sót đối tượng này.

### Không xác định loại tài khoản chỉ từ tên

| Dấu hiệu | Giá trị gợi ý | Giới hạn của dấu hiệu |
| --- | --- | --- |
| Tên chứa `svc`, `bot`, `job` hoặc `automation` | Có thể là tài khoản dịch vụ | Có thể đặt tên sai hoặc đã đổi mục đích |
| Có khai báo danh tính trong cấu hình dịch vụ | Cho biết thành phần dự kiến sử dụng | Cấu hình có thể cũ hoặc thành phần chưa chạy |
| Đăng nhập theo lịch, từ runner hoặc máy ứng dụng | Gợi ý hoạt động tự động | Chưa đủ để xác định toàn bộ bên sử dụng |
| Không có người dùng đăng nhập tương tác | Phù hợp một số loại workload | Không chứng minh tài khoản chỉ dành cho dịch vụ |
| Có credential trong kho bí mật | Cho biết có một đường phân phối credential | Không chứng minh credential chỉ được dùng từ kho đó |
| Có chủ sở hữu và tài liệu vận hành | Cung cấp ngữ cảnh công việc | Cần đối chiếu với trạng thái kỹ thuật hiện tại |

Phân loại ban đầu nên cho phép trạng thái **ứng viên tài khoản dịch vụ** và **chưa xác định**, thay vì ép mọi danh tính vào một kết luận chắc chắn.

## 2. Khi nào một service account được coi là mạnh?

Cần đánh giá khả năng trên tài nguyên và trong ngữ cảnh cụ thể. Một tài khoản có ít role nhưng được sửa phân quyền toàn tổ chức có thể mạnh hơn tài khoản có nhiều role chỉ đọc phạm vi hẹp.

Những khả năng đáng chú ý gồm:

| Nhóm khả năng | Ví dụ về tác động |
| --- | --- |
| Quản lý danh tính và quyền | Tạo principal, đổi trust, gán role hoặc sửa thành viên nhóm đặc quyền |
| Quản lý credential | Đặt lại, cấp mới, xuất hoặc lấy credential của tài khoản khác |
| Điều khiển thực thi | Sửa dịch vụ, job, pipeline hoặc workload chạy dưới danh tính mạnh hơn |
| Quản trị nền tảng | Quản trị nhiều máy chủ, cluster, tài khoản cloud hoặc cơ sở dữ liệu |
| Tác động dữ liệu | Đọc hàng loạt dữ liệu nhạy cảm, sửa dữ liệu quan trọng hoặc xóa diện rộng |
| Làm suy yếu khả năng giám sát | Sửa cấu hình audit, tác động tới log hoặc đường chuyển bằng chứng |
| Tác động phục hồi | Sửa, xóa hoặc vô hiệu hóa bản sao lưu và cấu hình phục hồi |
| Duy trì hoặc mở rộng quyền | Tạo credential dài hạn, principal mới hoặc cấp quyền cho chủ thể khác |

Không phải mọi tài khoản sao lưu đều là quản trị toàn hệ thống, cũng không phải mọi quyền chỉ đọc đều có rủi ro thấp. Cần xem dữ liệu có thể đọc, tài nguyên có thể chạm tới và khả năng kết hợp với quyền khác.

### Sức mạnh, mức phơi lộ và độ quan trọng là các chiều khác nhau

- **Sức mạnh:** tài khoản có thể làm gì và trên phạm vi nào.
- **Mức phơi lộ:** ai hoặc thành phần nào có thể lấy credential, điều khiển workload hay sử dụng danh tính.
- **Khả năng duy trì quyền:** quyền tồn tại bao lâu và có thể tạo quyền mới hay không.
- **Độ quan trọng vận hành:** dịch vụ phụ thuộc vào tài khoản và hậu quả nếu truy cập bị gián đoạn.

Một tài khoản mạnh nhưng được giới hạn chặt vẫn cần được quản lý. Một tài khoản quyền hẹp nhưng dùng chung trên nhiều hệ thống cũng cần điều tra mức phơi lộ. Không nên dùng một nhãn “an toàn” duy nhất để thay thế các chiều đánh giá này.

## 3. Xác định phạm vi discovery trước khi thu thập

Một lượt discovery cần nói rõ:

1. Những môi trường và hệ thống thuộc phạm vi, chẳng hạn production, máy chủ, cloud, cluster hoặc cơ sở dữ liệu.
2. Các loại danh tính được bao phủ và danh tính nào chưa có nguồn dữ liệu.
3. Những khả năng nhạy cảm dùng để tìm ứng viên mạnh.
4. Mốc chụp cấu hình và khoảng thời gian quan sát sử dụng.
5. Nhóm chịu trách nhiệm thu thập, xác minh và tiếp nhận phát hiện.

Định danh tài khoản bằng ID ổn định và ngữ cảnh hệ thống. Tên `svc-backup` trên hai máy khác nhau chưa chắc là cùng một chủ thể. Một danh tính nguồn và tài khoản được dùng ở đích cũng phải được lưu riêng, rồi liên kết bằng quan hệ có bằng chứng.

Đối với tài khoản đã xóa rồi tạo lại với cùng tên, lịch sử của chủ thể cũ không nên được gộp vào chủ thể mới chỉ vì tên hiển thị trùng nhau.

Không cần lấy giá trị bí mật để hoàn thành danh mục. Dữ liệu discovery nên dùng tham chiếu credential và thông tin vòng đời cần thiết, tránh sao chép token, mật khẩu hoặc private key.

## 4. Tìm ứng viên từ cả nơi cấp danh tính lẫn nơi chạy tác vụ

Chỉ xuất danh sách tài khoản từ directory sẽ bỏ sót tài khoản cục bộ, danh tính workload hoặc tài khoản trực tiếp trong ứng dụng. Chỉ đọc cấu hình workload cũng có thể bỏ sót principal còn tồn tại nhưng chưa rõ bên sử dụng.

| Nguồn | Thông tin cần lấy | Câu hỏi cần đối chiếu |
| --- | --- | --- |
| Directory, IdP và hệ thống IAM | ID, loại danh tính, nhóm, role, trạng thái, trust | Danh tính có tồn tại và nhận quyền bằng những đường nào? |
| Máy chủ, dịch vụ và bộ lập lịch | Danh tính thực thi, tên dịch vụ, tác vụ, cấu hình liên quan | Thành phần nào dự kiến chạy dưới tài khoản này? |
| Cloud và hệ thống điều phối | Danh tính gắn với workload, policy và cấu hình nhận danh tính | Workload nào có thể sử dụng hoặc yêu cầu danh tính đó? |
| CI/CD và runner | Job, pipeline, môi trường chạy, tham chiếu secret và quyền sửa | Ai có thể tác động tới mã chạy hoặc credential được cấp? |
| Cơ sở dữ liệu và ứng dụng | Tài khoản tại đích, role, quyền trên đối tượng | Tài khoản được phép làm gì sau khi kết nối? |
| Vault và cơ chế phát hành credential | Tham chiếu bí mật, bên được nhận, TTL hoặc thông tin luân chuyển nếu có | Ai lấy được credential và đích sử dụng là gì? |
| Audit và telemetry | Principal thực thi, nguồn, hành động, tài nguyên, kết quả | Sử dụng thực tế có phù hợp với cấu hình và mục đích không? |
| Hồ sơ vận hành | Chủ sở hữu, lịch chạy, phụ thuộc, quy trình phục hồi | Nhu cầu nào là hợp lệ và ai xác nhận? |

Với mỗi nguồn, ghi cả thời điểm thu thập và giới hạn bao phủ. Một máy chủ chưa kết nối được không được tính như đã kiểm tra và không có tài khoản mạnh.

### Đối chiếu cấu hình với thực thi

Cấu hình cho biết trạng thái dự kiến. Audit cho biết một số hoạt động đã diễn ra. Hai nguồn bổ sung cho nhau:

- Cấu hình có tài khoản nhưng chưa có log: kiểm tra lịch chạy, trạng thái triển khai và độ bao phủ log.
- Log có principal nhưng danh mục không có: tìm nguồn danh tính, tài khoản tại đích hoặc cơ chế giả danh.
- Cùng credential xuất hiện ở nhiều bên sử dụng: kiểm tra khả năng dùng chung và cách quy trách nhiệm.
- Một workload có nhiều danh tính: xác định danh tính nào thực hiện từng loại hành động.

Thiếu log không đủ để kết luận tài khoản không được dùng hoặc không còn cần thiết.

## 5. Nối tài khoản với workload, credential và chủ sở hữu

Danh mục cần trả lời được không chỉ “có tài khoản nào”, mà còn “ai sử dụng, ai điều khiển và ai chịu trách nhiệm”.

```text
Đội chủ sở hữu
     | chịu trách nhiệm vận hành
     v
Workload / job
     | chạy dưới hoặc nhận danh tính
     v
Service account
     | dùng credential hoặc cơ chế liên kết danh tính
     v
Tài nguyên đích

Người hoặc nhóm quản lý
     | có thể sửa workload, trust hoặc credential
     +--------------------> các mắt xích phía trên
```

Cần phân biệt ít nhất ba trách nhiệm:

- **Chủ sở hữu dịch vụ:** xác nhận nhiệm vụ và hậu quả vận hành.
- **Chủ sở hữu nền tảng hoặc tài nguyên:** xác nhận cơ chế phân quyền và phạm vi cho phép.
- **Bên quản lý danh tính/credential:** quản lý cấp phát, vòng đời và thu hồi.

Các trách nhiệm có thể thuộc cùng một đội nhưng không nên mặc định như vậy. Người tạo tài khoản trong quá khứ cũng chưa chắc là chủ sở hữu hiện tại.

### Một danh tính được dùng chung tạo hai vấn đề

Thứ nhất, mỗi bên dùng có thể nhận tổng quyền phục vụ nhiều nhiệm vụ khác nhau. Thứ hai, audit dưới một principal chung khó chỉ ra workload nào khởi tạo hành động nếu thiếu dữ liệu tương quan.

Không coi mỗi tham chiếu secret là một tài khoản mới. Cũng không gộp các tài khoản riêng chỉ vì cùng tên bí mật. Hãy lưu riêng các thực thể và quan hệ:

```text
Workload A ----> Secret reference 1 ----> Tài khoản tại đích Z
Workload B ----> Secret reference 2 ----> Tài khoản tại đích Z
```

Trong ví dụ này, hai tham chiếu có thể cùng dẫn tới tài khoản Z. Cần xác minh bằng dữ liệu quản lý và cấu hình phù hợp, không dựa vào việc xuất giá trị bí mật để so sánh.

## 6. Đánh giá quyền hiệu lực và khả năng gián tiếp

Với mỗi ứng viên, tìm các quan hệ gán trực tiếp, nhóm lồng nhau, kế thừa, chính sách tài nguyên, điều kiện và quyền nhận role. Cách đánh giá hiệu lực phụ thuộc quy tắc của hệ thống đích; không mặc định chỉ cần hợp tất cả role là có kết quả đúng.

Sau đó xem những khả năng cho phép tài khoản vượt khỏi nhiệm vụ ban đầu:

1. Có sửa được IAM, trust hoặc nhóm để cấp thêm quyền không?
2. Có đặt lại, cấp mới hoặc lấy credential của principal mạnh hơn không?
3. Có sửa mã, job hoặc workload chạy dưới danh tính mạnh hơn không?
4. Có gắn một danh tính khác vào thành phần mình kiểm soát không?
5. Có ghi vào cấu hình hoặc đầu vào mà tiến trình đặc quyền sẽ sử dụng không?
6. Có sửa audit, cơ chế phục hồi hoặc kiểm soát đang bảo vệ chính tài khoản không?

### Ví dụ đường quyền gián tiếp

```text
svc-report
    | được sửa cấu hình tác vụ
    v
Job export-production
    | thực thi dưới danh tính
    v
svc-data-admin
    | có quyền quản trị
    v
Cơ sở dữ liệu production
```

Đây là đường nghi vấn, chưa tự động chứng minh `svc-report` có toàn quyền ở cơ sở dữ liệu. Phải xác nhận quyền sửa có tác động tới logic thực thi, cấu hình đó được sử dụng, job có thể chạy và không có ranh giới kiểm soát làm đứt chuỗi.

Nếu quyền chỉ cho sửa mô tả của job, đường trên có thể không tồn tại như giả định. Nếu job bắt buộc dùng artifact đã được xác minh và phê duyệt độc lập, cần ghi điều kiện đó vào kết luận.

### Xem ai điều khiển tài khoản mạnh

Đánh giá service account phải bao gồm cả các chủ thể có thể sử dụng hoặc kiểm soát nó. Tài khoản có quyền rất hẹp ở lớp quản lý danh tính nhưng được nhiều runner không tin cậy nhận credential vẫn có thể gây rủi ro lớn.

Ngược lại, workload dùng credential ngắn hạn vẫn có thể nhận quyền quá rộng nếu trust hoặc điều kiện cấp credential cho phép quá nhiều chủ thể nguồn.

## 7. Đánh giá credential mà không thu thập giá trị bí mật

| Nội dung | Câu hỏi discovery |
| --- | --- |
| Cơ chế xác thực | Mật khẩu, khóa, chứng thư, token, liên kết danh tính hay cơ chế do nền tảng quản lý? |
| Bên phát hành | Ai có thể cấp mới, thay hoặc đặt lại credential? |
| Bên nhận | Workload, người hoặc nhóm nào có thể lấy hoặc sử dụng? |
| Vòng đời | Credential có hạn, có cơ chế hết hiệu lực và quy trình luân chuyển nào? |
| Phạm vi | Credential dùng được ở đích, môi trường và điều kiện nào? |
| Bản sao và phân phối | Có đường lưu trữ, đồng bộ hoặc triển khai ngoài cơ chế quản lý dự kiến không? |
| Thu hồi | Chặn cấp mới có xử lý credential đã phát hành và phiên tại đích không? |

Credential được nền tảng quản lý có thể giảm nhu cầu phân phối bí mật tĩnh, nhưng vẫn cần xem ai được gắn hoặc nhận danh tính và danh tính đó có quyền gì.

Vault hỗ trợ kiểm soát phát hành và vòng đời credential. Nó không tự thu hẹp quyền của tài khoản tại đích, cũng không tự bảo đảm mọi lần sử dụng credential đều đi qua một phiên được ghi lại.

Nếu phát hiện credential ngoài vùng quản lý, lưu tham chiếu vị trí và bên phụ thuộc theo quyền truy cập phù hợp. Tránh đưa nội dung credential vào báo cáo, ảnh chụp hoặc log của quá trình discovery.

## 8. Đọc audit đúng ngữ cảnh

Các sự kiện cần được liên kết với danh tính thực thi, tài nguyên, hành động, nguồn và thời điểm. Trong chuỗi tự động hóa có thể có nhiều principal:

```text
Người phê duyệt thay đổi
          |
          v
Pipeline / runner
          | nhận credential hoặc token
          v
Service account
          | kết nối
          v
Tài khoản hoặc principal tại hệ thống đích
```

Không gán hành động ở đích cho người phê duyệt chỉ vì họ xuất hiện đầu chuỗi. Cần bằng chứng tương quan giữa lần chạy, credential được cấp và principal thực hiện hành động.

Những dấu hiệu nên xác minh gồm:

- Tài khoản chỉ phục vụ tự động hóa nhưng có hoạt động tương tác ngoài mục đích đã xác nhận.
- Nguồn truy cập mới, môi trường mới hoặc hệ thống đích không thuộc danh mục.
- Hành động quản lý IAM, credential hoặc audit không nằm trong nhiệm vụ.
- Tài khoản dùng credential khác với cơ chế cấp phát đã khai báo.
- Hoạt động sau khi workload hoặc dự án liên quan đã ngừng.

Các dấu hiệu này là đầu vào điều tra. Một tác vụ phục hồi có thể chạy khác lịch thường ngày; một proxy có thể làm thay đổi địa chỉ nguồn nhìn thấy. Cần xác nhận ngữ cảnh trước khi kết luận hành vi trái phép.

Nếu không có cơ chế ghi phiên cho giao thức hoặc workload đó, ghi rõ giới hạn. Với tác vụ tự động, audit ứng dụng, nền tảng và credential broker có thể là nguồn bằng chứng quan trọng.

## 9. Ví dụ xuyên suốt: tài khoản phát hành dùng chung

Một tổ chức có ba pipeline: phát hành ứng dụng A, phát hành ứng dụng B và cập nhật cấu hình ứng dụng A. Cả ba dùng tài khoản `svc-release-shared`.

Danh mục ban đầu chỉ ghi “tài khoản CI/CD, đã lưu secret trong vault”. Discovery bổ sung được các thông tin minh họa:

| Hạng mục | Trạng thái tìm thấy |
| --- | --- |
| Quyền tại đích | Quản trị nhiều ứng dụng production, có khả năng sửa một số quan hệ IAM |
| Bên sử dụng | Ba pipeline trên hai nhóm runner |
| Credential | Một credential dài hạn được phân phối qua vault |
| Quyền điều khiển | Hai đội có thể sửa các phần khác nhau của pipeline |
| Nhu cầu hiện tại | Mỗi pipeline chỉ cần cập nhật tài nguyên ứng dụng được giao |
| Audit | Có log thao tác tại đích; liên kết tới từng lần chạy chưa đầy đủ |
| Chủ sở hữu | Đội nền tảng quản lý tài khoản; chủ sở hữu từng ứng dụng chưa cùng xác nhận quyền |

### Kết luận discovery

`svc-release-shared` là tài khoản mạnh vì có khả năng quản trị rộng và sửa phân quyền. Việc dùng chung mở rộng tập workload có thể sử dụng cùng khả năng. Dữ liệu audit chưa đủ để quy mọi thao tác cho đúng pipeline.

Không nên kết luận credential đã bị lộ chỉ vì nó được dùng chung. Cũng chưa nên giữ toàn bộ quyền chỉ vì một lần phát hành trước đây đã dùng tài khoản thành công.

### Phân tích nhu cầu

Cần cùng các chủ sở hữu xác nhận hành động, tài nguyên và điều kiện cần cho từng pipeline. Ngoài thao tác phát hành chính, cần xem những phụ thuộc hợp lệ như đọc artifact hoặc cập nhật cấu hình liên quan.

Nếu một pipeline cần thay IAM trong nhiệm vụ riêng, cần mô tả nhiệm vụ và ranh giới của nó, thay vì để mọi lần phát hành giữ khả năng quản lý IAM tổng quát.

### Hướng xử lý bàn giao

Một phương án là tách danh tính theo workload và môi trường, cấp tập quyền hẹp tương ứng rồi chuyển sang cơ chế nhận credential phù hợp. Khi có thể, sử dụng credential ngắn hạn với điều kiện nhận danh tính rõ ràng.

Trước khi thu hồi tài khoản hoặc credential cũ, cần xác định đầy đủ bên phụ thuộc, xác nhận lần chạy hợp lệ với danh tính mới và xử lý đường cấp credential cũ. Nếu credential từng được phân phối ra ngoài vault, cần tính đến bản sao và khả năng còn dùng được tại đích.

Với audit, cần bổ sung thông tin tương quan giữa pipeline, lần chạy và principal ở đích. Tách danh tính cải thiện khả năng quy trách nhiệm nhưng không thay thế việc thu thập log đủ ngữ cảnh.

## 10. Xếp ưu tiên mà không đánh đồng mọi tài khoản

Phân loại nên dựa trên khả năng nhạy cảm và bằng chứng, thay vì tự đặt một ngưỡng số role hoặc số ngày không dùng cho mọi hệ thống.

| Chiều đánh giá | Dấu hiệu cần xem xét sớm |
| --- | --- |
| Tác động | Quản lý IAM, credential, dữ liệu nhạy cảm, audit hoặc phục hồi |
| Phạm vi | Nhiều môi trường, nhiều ứng dụng hoặc phạm vi tổ chức |
| Khả năng sử dụng sai | Nhiều bên nhận credential, runner không được giới hạn hoặc quyền sửa workload quá rộng |
| Duy trì quyền | Credential dài hạn, tự tạo khóa hoặc cấp quyền bền vững |
| Quản trị vòng đời | Không rõ chủ sở hữu, không rõ workload phụ thuộc hoặc ngoại lệ không có hạn |
| Khả năng phát hiện | Thiếu audit, không liên kết được hành động với bên sử dụng |
| Phụ thuộc vận hành | Dịch vụ trọng yếu, job hiếm gặp hoặc chức năng phục hồi |

Độ quan trọng vận hành ảnh hưởng cách xử lý an toàn, không phải lý do mặc định giữ quyền rộng vĩnh viễn. Tài khoản phục hồi có thể cần khả năng lớn nhưng vẫn cần chủ sở hữu, điều kiện sử dụng và cơ chế kiểm tra phù hợp.

### Tách mức rủi ro khỏi độ chắc chắn

Một tài khoản có đường nghi vấn tới quyền quản trị toàn tổ chức có thể cần ưu tiên xác minh cao dù chưa đủ bằng chứng kết luận. Một tài khoản đã xác minh có quyền rộng nhưng trong môi trường thử nghiệm cô lập có thể có thứ tự xử lý khác.

Có thể ghi các trạng thái xác minh sau:

- **Ứng viên mạnh:** có dấu hiệu nhưng chưa đánh giá đủ quyền và điều kiện.
- **Được hỗ trợ bởi cấu hình:** các quyền, scope và điều kiện đã được đối chiếu trong phạm vi xác định.
- **Đã quan sát sử dụng:** audit cho thấy một khả năng đã được dùng trong ngữ cảnh cụ thể.
- **Chưa đủ dữ liệu:** thiếu nguồn hoặc chưa giải thích được mắt xích quan trọng.

Quyền đã được dùng không chứng minh quyền đó còn cần thiết. Quyền chưa được dùng cũng không chứng minh có thể thu hồi ngay.

## 11. Tạo hồ sơ phát hiện có thể bàn giao

Hồ sơ cần đủ thông tin để đội tiếp nhận hiểu tài khoản mạnh ở đâu, vì sao kết luận như vậy và điều gì còn chưa rõ.

| Nhóm thông tin | Nội dung tối thiểu |
| --- | --- |
| Định danh | ID, loại danh tính, hệ thống và môi trường |
| Quan hệ sử dụng | Workload, job, runner hoặc dịch vụ đã xác minh |
| Chủ sở hữu | Đội dịch vụ, nền tảng và bên quản lý credential |
| Nhu cầu | Nhiệm vụ, hành động và tài nguyên được xác nhận |
| Khả năng | Quyền hiệu lực, đường gián tiếp, scope và điều kiện |
| Credential | Cơ chế, tham chiếu, vòng đời và bên được nhận; không có giá trị bí mật |
| Bằng chứng | Snapshot, policy, audit, mốc thời gian và nguồn |
| Giới hạn | Phần chưa bao phủ, bên phụ thuộc chưa rõ, độ chắc chắn |
| Bàn giao | Ưu tiên, bên chủ trì, bước tiếp theo và cách xác minh |

Ví dụ dưới đây là **hồ sơ minh họa**, không phải cấu hình của một công cụ:

```yaml
finding:
  id: pam-service-account-example-006
  identity:
    reference: iam-example/svc-release-shared
    type: automation-account
    environment: production
  owners:
    platform: platform-operations
    business_need_confirmation: application-owners-pending
  consumers:
    - pipeline-application-a-release
    - pipeline-application-b-release
    - pipeline-application-a-config
  capabilities:
    - administer-multiple-production-applications
    - modify-selected-iam-bindings
  credential:
    reference: vault-example/release-shared
    lifecycle: long-lived
    distribution_coverage: requires-confirmation
  verification: supported-by-configuration
  evidence_ref: protected-evidence/service-account-discovery-006
  limitations:
    - incomplete-run-to-target-audit-correlation
  next_actions:
    - confirm-required-capabilities-per-workload
    - design-separated-identities-and-scopes
    - plan-credential-and-session-transition
```

Trong hồ sơ thật, mỗi khả năng nhạy cảm cần dẫn tới bằng chứng tương ứng. Không dùng tên role làm bằng chứng duy nhất cho mức quản trị. Với dữ liệu từ nhiều thời điểm, cần xác định liệu các quan hệ có cùng tồn tại trong khoảng kết luận hay không.

## 12. Từ phát hiện tới kiểm soát PAM

Discovery cung cấp đầu vào cho xử lý; nó không thay thế phân tích phụ thuộc và xác nhận nhu cầu. Biện pháp cần phù hợp với loại workload.

| Phát hiện | Hướng kiểm soát | Điểm cần xác nhận |
| --- | --- | --- |
| Quyền vượt nhiệm vụ | Least privilege theo hành động, tài nguyên và môi trường | Tác vụ hợp lệ vẫn hoạt động; khả năng dư đã mất |
| Một danh tính cho nhiều workload | Tách danh tính và phạm vi credential | Không còn workload vô tình nhận quyền của bên khác |
| Credential tĩnh phân phối rộng | Vault, quản lý bản sao và luân chuyển theo kế hoạch | Credential cũ không còn dùng được theo mục tiêu thay đổi |
| Workload có thể nhận credential ngắn hạn | Cấp credential theo danh tính và điều kiện phù hợp | Trust, nguồn yêu cầu và scope không cho nhận quyền ngoài nhiệm vụ |
| Nhiệm vụ nhạy cảm chỉ xảy ra theo đợt | JIT hoặc cơ chế cấp quyền tạm thời có kiểm soát | Cấp mới, hết hạn, phiên và quyền phát sinh được xử lý |
| Công việc quản trị có tập thao tác xác định | JEA hoặc giao diện tác vụ được giới hạn | Tham số, đích và mã thực thi không mở lại quyền tùy ý |
| Không xác định được bên sử dụng | Tìm chủ sở hữu và phụ thuộc; áp dụng quy trình tài khoản chưa rõ chủ | Không tự xóa dựa riêng vào thiếu log hoặc thiếu tên chủ sở hữu |
| Thiếu bằng chứng sử dụng | Bổ sung audit và tương quan theo workload | Có thể liên kết hành động nhạy cảm với đúng danh tính và lần chạy |

### Tự động hóa cần cơ chế cấp quyền phù hợp

Không mặc định mọi lần chạy service account đều phải chờ một người phê duyệt tương tác. Với workload hợp lệ, điều kiện cấp quyền có thể dựa trên danh tính nguồn, môi trường, loại tác vụ và chính sách đã được chấp nhận.

Cần bảo vệ chính những điều kiện này. Nếu một bên được tùy ý sửa workload và điều kiện nhận danh tính, credential ngắn hạn vẫn có thể cấp quyền rộng cho hành vi ngoài nhiệm vụ.

### Luân chuyển credential không giảm quyền hiệu lực

Luân chuyển thay đổi credential, còn least privilege thay đổi khả năng được phép. Hai công việc bổ sung cho nhau. Đổi mật khẩu của tài khoản quản trị rộng không làm tài khoản đó trở thành quyền hẹp.

Tương tự, chặn lấy bí mật mới từ vault chưa chắc vô hiệu hóa bản sao đã lấy hoặc kết thúc phiên tại đích. Cơ chế thu hồi phải được xác minh theo nền tảng.

### Xử lý theo mức khẩn cấp thực tế

Nếu có dấu hiệu credential bị lộ hoặc tài khoản đang bị lạm dụng, chuyển sang quy trình ứng phó, bảo toàn bằng chứng và hạn chế tác động phù hợp. Không chờ đợt review hoàn tất.

Nếu chưa có dấu hiệu sự cố, việc chuyển đổi cần có kế hoạch phụ thuộc và khôi phục vận hành. Trường hợp phải giữ quyền rộng tạm thời cần ghi chủ sở hữu, lý do, biện pháp bù đắp, thời hạn và tiêu chí kết thúc ngoại lệ.

## 13. Những sai lầm thường gặp

### Chỉ tìm tên tài khoản dịch vụ

Tiền tố tên là gợi ý, không phải cơ chế xác minh. Cần tìm cả tài khoản người dùng đang được tự động hóa sử dụng và danh tính workload không có mật khẩu.

### Chỉ tìm tài khoản có role quản trị trực tiếp

Quyền sửa trust, lấy credential mạnh hơn hoặc điều khiển job đặc quyền có thể tạo sức mạnh gián tiếp. Cần ghi từng mắt xích và điều kiện, không suy luận từ một cạnh đơn lẻ.

### Đánh dấu rủi ro thấp vì secret nằm trong vault

Cần kiểm tra ai lấy được secret, principal ở đích có quyền gì và credential có thể được sử dụng ngoài luồng dự kiến không.

### Thu hồi theo trường “last used” duy nhất

Job theo quý, công việc phục hồi hoặc audit thiếu bao phủ có thể không xuất hiện trong khoảng quan sát. Cần lịch công việc, dữ liệu cấu hình và xác nhận của chủ sở hữu.

### Chỉ đếm số tài khoản đã tìm thấy

Tìm thấy nhiều tài khoản chưa chứng minh đã bao phủ đủ hệ thống hoặc hiểu được quyền. Cần theo dõi cả nguồn chưa quét, tài khoản chưa rõ chủ và trường hợp chưa đánh giá quyền.

### Giảm quyền nhưng bỏ qua credential, trust và phiên

Quyền hiện tại và trạng thái truy cập đã phát hành là các lớp khác nhau. Cần xác nhận các đường còn lại sau thay đổi, đặc biệt khi chuyển khỏi danh tính dùng chung.

## 14. Tình huống tự đánh giá

Một đợt discovery tìm thấy bốn tài khoản:

| Tài khoản | Thông tin hiện có |
| --- | --- |
| A | Có quyền sửa IAM production; dùng credential ngắn hạn; nhiều runner có thể nhận danh tính |
| B | Chỉ đọc dữ liệu trong một kho thử nghiệm; credential dài hạn; chưa rõ chủ sở hữu |
| C | Có quyền quản trị phục hồi; không có log trong khoảng quan sát; có tài liệu công việc khẩn cấp |
| D | Không có role quản trị trực tiếp; có thể sửa logic một job chạy dưới tài khoản mạnh hơn |

### Phân tích mẫu

**A:** là ứng viên mạnh vì khả năng sửa IAM production. Credential ngắn hạn không loại bỏ sức mạnh đó. Cần xác minh điều kiện nhận danh tính, runner được phép và quyền tạo ra trong thời gian phiên có hiệu lực.

**B:** chưa có bằng chứng tài khoản mạnh theo phạm vi đã biết, nhưng có vấn đề về chủ sở hữu và vòng đời credential. Cần xác nhận dữ liệu có thực sự ít nhạy cảm, scope có đúng và còn bên sử dụng nào chưa phát hiện.

**C:** có khả năng nhạy cảm nhưng có thể phục vụ nhu cầu hợp lệ. Thiếu log chưa đủ để thu hồi. Cần xác nhận chủ sở hữu, điều kiện sử dụng, khả năng phục hồi và cơ chế bảo vệ credential.

**D:** có đường đặc quyền gián tiếp cần kiểm tra. Phải xác nhận thay đổi của D có thể đi vào lần thực thi, có bước kiểm duyệt hoặc ranh giới nào chặn chuỗi và quyền tài khoản thực thi áp dụng ở đâu.

Không có đủ dữ liệu để xếp thứ tự tuyệt đối cả bốn trường hợp. Tuy nhiên, khả năng quản lý IAM của A và đường nghi vấn của D đáng được xác minh sớm; B và C cần được xử lý theo rủi ro và phụ thuộc riêng.

## 15. Kết quả cần có sau một lượt discovery

Một lượt discovery có thể bàn giao khi:

- Phạm vi, mốc dữ liệu và các nguồn chưa bao phủ được ghi rõ.
- Tài khoản được định danh trong đúng hệ thống, với loại danh tính chính xác.
- Có quan hệ tới workload, chủ sở hữu và credential; phần chưa xác minh được đánh dấu.
- Khả năng nhạy cảm có bằng chứng về hành động, tài nguyên, scope và điều kiện.
- Đường quyền gián tiếp được phân biệt với quyền trực tiếp và suy đoán chưa đủ dữ liệu.
- Có mức ưu tiên, bên tiếp nhận và bước xác minh hoặc giảm quyền tiếp theo.
- Hồ sơ không chứa giá trị credential có thể sử dụng.

Các chỉ số hỗ trợ quản lý có thể gồm tỷ lệ tài khoản đã xác minh chủ sở hữu, tỷ lệ đã phân tích quyền, số tài khoản mạnh dùng chung và số phát hiện chưa có bên xử lý. Cần dùng mẫu số rõ ràng: tỷ lệ trên tập tài khoản đã phát hiện không chứng minh đã bao phủ toàn bộ hạ tầng.

Discovery cần được cập nhật khi workload, nhóm, role, trust, credential hoặc chủ sở hữu thay đổi. Một danh tính từng có phạm vi hẹp có thể trở nên mạnh sau khi role được mở rộng hoặc workload được chuyển sang môi trường nhạy cảm.

Điều cần ghi nhớ là **sức mạnh của service account nằm ở khả năng thực tế, phạm vi tác động và những chủ thể có thể điều khiển nó**. Danh mục tốt phải nối được các yếu tố này với nhu cầu công việc và bằng chứng, để PAM có cơ sở giảm đặc quyền và kiểm soát truy cập bền vững.
