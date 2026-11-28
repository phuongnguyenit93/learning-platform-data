# Phát hiện quyền ẩn

## Mục tiêu bài học

Trong chương **Discovery** của quản lý truy cập đặc quyền (**Privileged Access Management — PAM**), phát hiện quyền ẩn là tìm ra những khả năng mà danh tính có thể thực hiện nhưng chưa được phản ánh đầy đủ trong danh mục quyền đang rà soát. Đối tượng gồm tài khoản quản trị, tài khoản dịch vụ, workload và các đường truy cập đến hạ tầng nhạy cảm.

Quyền ẩn thường hình thành từ nhóm lồng nhau, kế thừa, quan hệ tin cậy, credential hoặc khả năng điều khiển một thành phần chạy dưới danh tính mạnh hơn. Chúng có thể tồn tại trong cấu hình hợp lệ; không nhất thiết là cửa hậu hoặc dấu hiệu bị tấn công.

Sau bài học, bạn có thể:

- Phân biệt quyền được gán trực tiếp, quyền hiệu lực và khả năng đặc quyền gián tiếp.
- Lần theo các đường nhận quyền qua nhóm, role, bí mật, workload và công cụ vận hành.
- Ghi nhận điều kiện, nguồn bằng chứng và giới hạn quan sát của từng đường quyền.
- Xác minh phát hiện mà không cần thực hiện hành động gây tác động trên production.
- Chuyển phát hiện thành đầu vào cho least privilege, JIT/JEA, vault, luân chuyển credential và giám sát phiên.

## 1. Quyền ẩn là gì và ẩn đối với ai?

**Quyền ẩn là khả năng chưa hiện rõ trong góc nhìn quản lý hiện tại, dù có thể được tạo ra bởi một hoặc nhiều quan hệ truy cập.** Từ “ẩn” mô tả khoảng trống trong khả năng quan sát, không phải một loại quyền riêng của mọi nền tảng.

Ví dụ, danh mục PAM ghi tài khoản `ops-minh` không có role quản trị cơ sở dữ liệu. Tuy nhiên, tài khoản này có thể chỉnh sửa một job sao lưu chạy dưới tài khoản dịch vụ có quyền quản trị cơ sở dữ liệu. Nếu việc chỉnh sửa cho phép thay lệnh thực thi và không có ranh giới kiểm soát phù hợp, đây là một đường đặc quyền gián tiếp cần được điều tra.

Cùng một quyền có thể hiện rõ với đội vận hành nhưng bị bỏ sót trong đợt review của đội IAM. Vì vậy, phát hiện quyền ẩn cần đối chiếu nhiều lớp dữ liệu, thay vì chỉ tìm một cờ tên là “admin”.

### Ba khái niệm cần tách biệt

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| Quyền được gán | Cấu hình đã cấp gì cho chủ thể? | Thành viên của nhóm vận hành |
| Quyền hiệu lực | Trong ngữ cảnh cụ thể, cơ chế phân quyền thực sự cho phép gì? | Được sửa cấu hình dịch vụ A sau khi xét scope và điều kiện |
| Khả năng đặc quyền gián tiếp | Chủ thể có thể tác động qua trung gian để nhận hoặc sử dụng đặc quyền nào? | Sửa workload chạy dưới tài khoản mạnh hơn |

Quyền hiệu lực phải được đánh giá theo quy tắc của hệ thống đích. Khả năng gián tiếp còn đòi hỏi xem xét dữ liệu, quy trình, credential và ranh giới giữa các hệ thống.

## 2. Những hình thức thường bị bỏ sót

| Nguồn quyền | Vì sao dễ bị bỏ sót | Điều cần kiểm tra |
| --- | --- | --- |
| Nhóm lồng nhau hoặc kế thừa | Chỉ kiểm kê thành viên trực tiếp hoặc tài nguyên con | Chuỗi nhóm, phạm vi cha và khả năng kế thừa |
| Role đủ điều kiện kích hoạt | Chỉ liệt kê role đang hoạt động | Ai được kích hoạt, ai phê duyệt, điều kiện và thời hạn |
| Quan hệ tin cậy | Chỉ nhìn role đích, không nhìn ai có thể nhận role | Principal nguồn, trust và quyền cho phép ở các phía liên quan |
| Chính sách trên tài nguyên | Quyền không xuất hiện trong danh sách role của người dùng | Tài nguyên cho phép những principal nào và trong điều kiện nào |
| Tài khoản cục bộ hoặc truy cập trực tiếp | Nằm ngoài danh mục danh tính trung tâm | Máy chủ, cơ sở dữ liệu, thiết bị mạng và đường quản trị riêng |
| Vault và bí mật | Chỉ đếm quyền truy cập vault | Bí mật nào được lấy và credential đó mạnh đến đâu ở đích |
| Workload, pipeline, tác vụ định kỳ | Danh tính người chỉnh cấu hình khác danh tính thực thi | Ai sửa được mã, tham số, artifact hoặc danh tính chạy |
| Công cụ quản trị hoặc runner | Giao diện trông như một tác vụ hẹp | Phạm vi đích, đầu vào, khả năng chạy lệnh và credential phía sau |
| Credential và phiên đã phát hành | Danh sách cấp quyền hiện tại không phản ánh toàn bộ trạng thái đang tồn tại | Token, khóa, mật khẩu đã phân phối và phiên còn hiệu lực |

Không phải quan hệ nào trong bảng cũng dẫn đến đặc quyền. Mỗi trường hợp cần kiểm tra khả năng cụ thể và các điều kiện ngăn chặn hoặc cho phép đường đó.

## 3. Mô hình hóa đường quyền theo khả năng

Một dòng “user có role X” thường không đủ để mô tả quyền ẩn. Có thể dùng mô hình gồm **chủ thể, hành động, đối tượng, điều kiện và bằng chứng**.

```text
Chủ thể A
   | có thể sửa cấu hình của
   v
Job B
   | được thực thi dưới danh tính
   v
Tài khoản dịch vụ C
   | được phép ghi vào
   v
Tài nguyên nhạy cảm D
```

Đường này chỉ trở thành khả năng thực tế của A khi các mắt xích liên quan thực sự kết hợp được. Chẳng hạn:

- A sửa được nội dung có ảnh hưởng đến hành vi thực thi, không chỉ sửa nhãn mô tả.
- Cấu hình sửa đổi được sử dụng trong lần chạy hợp lệ.
- Có cách kích hoạt hoặc chờ job chạy trong điều kiện khả dụng.
- Bước phê duyệt, xác minh artifact hoặc ranh giới thực thi không chặn thay đổi đó.
- Quyền của C có hiệu lực trên đúng tài nguyên D.

Nếu một mắt xích chưa có bằng chứng, hãy ghi **đường quyền nghi vấn**, kèm phần chưa xác minh. Không chuyển suy đoán thành kết luận “A đã có toàn quyền”.

### Có đồ thị kết nối chưa đồng nghĩa có quyền thực thi

Đồ thị giúp tìm quan hệ nhưng có thể ghép những điều kiện không tương thích. Một quyền chỉ áp dụng ở môi trường thử nghiệm không tự nối được với một tài nguyên production. Hai quyền tồn tại ở hai thời điểm khác nhau cũng không chứng minh một chuỗi khả dụng tại cùng thời điểm.

Ngoài ra, mô hình cho phép và từ chối khác nhau giữa các nền tảng. Không dùng một công thức hợp role đơn giản cho mọi hệ thống. Cần xét phạm vi, điều kiện, ranh giới phân quyền và các quy tắc ưu tiên áp dụng tại đích.

## 4. Bắt đầu từ phạm vi và định danh ổn định

Trước khi thu thập, cần xác định rõ:

1. Hệ thống và môi trường nằm trong phạm vi discovery.
2. Các tài nguyên nhạy cảm cần bảo vệ.
3. Nhóm danh tính cần xem: người dùng, dịch vụ, workload, bên thứ ba và tài khoản khẩn cấp.
4. Mốc chụp cấu hình và khoảng quan sát audit.
5. Nguồn nào đã bao phủ và nguồn nào chưa truy cập được.
6. Người chịu trách nhiệm xác nhận hệ thống, danh tính và phát hiện.

Tên hiển thị không phải định danh đáng tin cậy để nối dữ liệu. Hai tài khoản cùng tên có thể thuộc hai máy, domain hoặc tenant khác nhau. Một tên tài khoản đã xóa có thể được dùng lại cho chủ thể mới.

Hồ sơ nên lưu định danh ổn định theo cơ chế nền tảng và ngữ cảnh của nó, chẳng hạn directory/domain/tenant, host hoặc hệ thống đích. Khi ánh xạ một người sang nhiều tài khoản quản trị, vẫn giữ riêng định danh kỹ thuật của từng tài khoản.

Nếu chưa xác định được chủ sở hữu, ghi rõ trạng thái chưa xác định. Không gán chủ sở hữu chỉ dựa vào tiền tố tài khoản hoặc tên nhóm.

## 5. Thu thập từ các lớp kiểm soát liên quan

### 5.1. Lớp danh tính và cấp quyền

Thu thập quan hệ thành viên nhóm, quan hệ gán role, quyền đủ điều kiện kích hoạt, quan hệ tin cậy và chính sách trên tài nguyên. Với cấu trúc kế thừa, cần biết quyền xuất phát từ đâu và áp dụng tới phạm vi nào.

Cần xem cả quyền quản lý các quan hệ đó. Một người chưa có role nhạy cảm nhưng được sửa thành viên của nhóm sở hữu role có thể có đường tự nâng quyền.

### 5.2. Lớp hệ điều hành và nền tảng

Xem tài khoản cục bộ, nhóm quản trị, quyền chạy tác vụ đặc quyền, quyền sửa dịch vụ và quyền trên file hoặc cấu hình mà tiến trình đặc quyền sử dụng. Mục tiêu là xác định ai có thể thay đổi hành vi của thành phần chạy với quyền cao hơn.

Không coi mọi quyền ghi file là đường quản trị. Cần biết file có thực sự được đọc hoặc thực thi, khi nào được dùng và có cơ chế kiểm tra tính toàn vẹn hay ranh giới bảo vệ nào.

### 5.3. Lớp workload và chuỗi triển khai

Xem ai được sửa pipeline, cấu hình job, tham chiếu artifact, thông số triển khai, danh tính workload và runner. Phân biệt quyền chỉnh sửa với quyền hợp nhất, phê duyệt, chạy và phát hành.

Một người được sửa mã trong nhánh cá nhân chưa chắc thay được nội dung triển khai production. Ngược lại, quyền sửa cấu hình runner dùng chung có thể tác động tới nhiều workload hơn một quyền phát hành đơn lẻ.

### 5.4. Lớp bí mật và credential

Xem ai được đọc, xuất, đồng bộ, đặt lại hoặc thay credential; ai được sửa chính sách vault; và tài khoản ở đích có khả năng gì.

Không lấy giá trị bí mật để đưa vào danh mục discovery. Dùng mã tham chiếu bí mật, loại credential, chủ sở hữu, đích sử dụng và thông tin vòng đời cần thiết. Nếu cần xác minh kỹ thuật, dùng luồng được kiểm soát và tránh đưa bí mật vào log hoặc hồ sơ.

### 5.5. Lớp audit và phiên

Audit giúp biết các đường quyền đã được sử dụng như thế nào, nhưng không thay thế việc đọc cấu hình. Quyền có thể tồn tại mà chưa được sử dụng trong khoảng quan sát.

Khi có PAM broker hoặc cơ chế ghi phiên, đối chiếu danh tính khởi tạo, credential được dùng và principal ở đích. Một phiên được ghi hình không tự chứng minh mọi đường truy cập trực tiếp đến đích đã được bao phủ.

## 6. Lần theo cả hai chiều

**Đi từ chủ thể** giúp trả lời một tài khoản có thể làm gì. **Đi từ tài nguyên nhạy cảm** giúp trả lời ai có thể tác động đến tài nguyên đó.

Ví dụ với cơ sở dữ liệu production:

```text
Cơ sở dữ liệu production
    ^
    | tài khoản có quyền quản trị
    |
Tài khoản dịch vụ db-maint
    ^                         ^
    | dùng credential         | có thể đặt lại hoặc thay credential
    |                         |
Job bảo trì                Nhóm quản lý credential
    ^
    | có thể sửa logic chạy
    |
Nhóm vận hành job
```

Chỉ xuất danh sách người có role quản trị trực tiếp trên cơ sở dữ liệu sẽ bỏ sót các chủ thể điều khiển job hoặc quản lý credential.

Với mỗi nhánh, hỏi tiếp:

- Ai sửa được nhóm hoặc policy đang cho phép hành động này?
- Có đường truy cập cục bộ hoặc credential ngoài PAM không?
- Principal trung gian còn dùng chung cho dịch vụ nào?
- Điều kiện nào giới hạn tài nguyên, thời gian hoặc nguồn truy cập?
- Có bằng chứng về ranh giới ngăn các quyền kết hợp với nhau không?

Nên ưu tiên các đường kết thúc ở tài nguyên nhạy cảm và khả năng sửa chính sách, danh tính hoặc bằng chứng audit. Với hệ thống lớn, giới hạn độ sâu tìm kiếm phải được ghi lại như giới hạn bao phủ; không diễn giải “chưa tìm thấy trong giới hạn đã quét” thành “không tồn tại”.

## 7. Một số bối cảnh dễ hiểu nhầm

Các ví dụ dưới đây là hướng đặt câu hỏi, không phải kết luận tự động cho mọi cấu hình.

| Bối cảnh | Câu hỏi discovery | Điều cần tránh kết luận vội |
| --- | --- | --- |
| Windows hoặc directory | Ai sửa được thành viên nhóm, cấu hình tác vụ, dịch vụ hoặc đối tượng liên quan đến quản trị? | Mọi quyền sửa thuộc tính đều tương đương quản trị toàn domain |
| Linux hoặc Unix | Ai được chạy tác vụ đặc quyền và ai sửa được chương trình, script, cấu hình mà tác vụ đó sử dụng? | Có quyền chạy một lệnh là có thể chạy mọi lệnh |
| Kubernetes | Ai tạo hoặc sửa workload, workload dùng service account nào và bị giới hạn bởi những kiểm soát nào? | Quyền tạo pod luôn đồng nghĩa quản trị cluster |
| Cloud IAM | Ai có thể nhận role, gắn danh tính cho workload hoặc sửa policy và quan hệ tin cậy? | Chỉ một phía cho phép là đủ để nhận mọi role |
| CI/CD | Ai thay được nội dung được thực thi, artifact, runner hoặc credential phát hành? | Quyền đọc repository là quyền phát hành production |
| Vault | Ai lấy hoặc thay được bí mật của principal mạnh hơn? | Có vault đồng nghĩa credential đã không còn đường sử dụng trực tiếp |
| Cơ sở dữ liệu hoặc thiết bị mạng | Có tài khoản cục bộ, role kế thừa hoặc tích hợp xác thực nào ngoài danh mục trung tâm? | Danh sách ở IdP phản ánh đầy đủ quyền tại đích |

Việc xác nhận phải dựa trên cấu hình và hành vi của hệ thống cụ thể. Với quyền có điều kiện, ghi cả điều kiện và khả năng thay đổi điều kiện đó.

## 8. Ví dụ xuyên suốt: tài khoản không có role production trực tiếp

Trong danh mục ban đầu, tài khoản `ops-lan` chỉ thuộc nhóm `automation-maintainers`. Đội review cho rằng tài khoản này không có đặc quyền production vì không được gán role tại cơ sở dữ liệu.

Discovery thu được các bằng chứng minh họa:

1. `ops-lan` là thành viên hợp lệ của `automation-maintainers`.
2. Nhóm này được sửa nội dung tác vụ bảo trì `inventory-maint`.
3. Tác vụ chạy theo lịch dưới danh tính `svc-inventory-maint`.
4. Tác vụ lấy credential từ vault để truy cập cơ sở dữ liệu production.
5. Tài khoản cơ sở dữ liệu tương ứng đang có quyền quản trị rộng.

Đây mới là chuỗi nghi vấn. Người phân tích cần xác nhận:

- Quyền sửa tác vụ có bao gồm lệnh hoặc mã thực thi không?
- Có bước kiểm duyệt độc lập trước khi thay đổi có hiệu lực không?
- Job có thể sử dụng credential để thực hiện hành động tùy ý hay chỉ qua một giao diện có giới hạn?
- Tài khoản ở đích thực sự có những quyền gì?
- Có hạn chế nguồn, mạng, thời gian hoặc cơ chế thực thi làm đứt chuỗi không?

Giả sử bằng chứng cấu hình xác nhận nhóm có thể sửa logic thực thi, job tự chạy theo lịch và không có bước phê duyệt độc lập cho thay đổi đó. Khi ấy có cơ sở ghi nhận một đường sử dụng đặc quyền gián tiếp từ `ops-lan` tới cơ sở dữ liệu.

### Cách mô tả phát hiện

> Tại thời điểm chụp cấu hình, thành viên nhóm `automation-maintainers` có thể thay logic của tác vụ `inventory-maint`. Tác vụ này dùng credential của tài khoản quản trị cơ sở dữ liệu production. Đường quyền chưa được phản ánh trong danh mục quyền của các thành viên nhóm; cần xác nhận nhu cầu, thu hẹp khả năng và quản lý credential liên quan.

Mô tả này chỉ ra cơ chế và phạm vi. Nó không khẳng định tài khoản đã lạm dụng quyền hoặc đã đọc dữ liệu khi chưa có bằng chứng.

### Tác động của phát hiện tới PAM

Nhóm xử lý có thể cân nhắc tách quyền sửa tác vụ khỏi quyền phê duyệt, giới hạn thao tác của tài khoản dịch vụ và dùng danh tính riêng cho từng nhiệm vụ. Nếu có nhu cầu vận hành hiếm gặp, có thể thiết kế JIT hoặc JEA phù hợp.

Chỉ đặt credential vào vault chưa giải quyết quyền sửa job đang sử dụng credential đó. Chỉ ghi phiên của tài khoản người dùng cũng chưa chắc bao phủ lần thực thi tự động dưới danh tính dịch vụ.

## 9. Xác minh mà không tạo tác động ngoài mục tiêu

Discovery cần chứng minh đường quyền bằng mức bằng chứng phù hợp. Không cần đăng nhập bằng credential nhạy cảm hoặc thực hiện thao tác phá hủy chỉ để chứng minh nguy cơ.

Một trình tự xác minh có thể là:

1. **Đối chiếu cấu hình:** xác nhận từng quan hệ, định danh, scope và mốc thời gian.
2. **Đánh giá điều kiện:** kiểm tra phê duyệt, thời hạn, hạn chế nguồn, chính sách từ chối và ranh giới thực thi có liên quan.
3. **Dùng khả năng đánh giá của nền tảng:** nếu có, sử dụng công cụ kiểm tra quyền hoặc mô phỏng và ghi rõ phạm vi nó hỗ trợ.
4. **Xác nhận với chủ sở hữu:** làm rõ cách thành phần thực sự vận hành và các bước chưa xuất hiện trong dữ liệu.
5. **Kiểm tra thực thi khi cần:** dùng môi trường, dữ liệu và thao tác an toàn nằm trong phạm vi được giao.

Công cụ mô phỏng có thể không mô hình hóa đầy đủ ứng dụng, phiên hiện tại, chính sách bên ngoài hoặc luồng lấy credential. Kết quả cho một lời gọi API cũng không tự chứng minh toàn bộ chuỗi ứng dụng.

### Phân loại độ chắc chắn

| Trạng thái | Ý nghĩa |
| --- | --- |
| Nghi vấn | Có một phần quan hệ nhưng thiếu mắt xích hoặc điều kiện |
| Được hỗ trợ bởi cấu hình | Có bằng chứng cấu hình cho các mắt xích và điều kiện đã xét |
| Đã quan sát sử dụng | Audit cho thấy đường quyền được dùng trong một ngữ cảnh xác định |
| Bị chặn trong ngữ cảnh đã kiểm tra | Có ranh giới ngăn đường quyền ở điều kiện cụ thể đã xác minh |
| Chưa đủ dữ liệu | Nguồn hoặc độ bao phủ chưa cho phép kết luận |

“Đã quan sát sử dụng” không đồng nghĩa đã bị lạm dụng. “Bị chặn” cũng không chứng minh không còn đường khác. Luôn kèm ngữ cảnh, thời điểm và giới hạn của kết luận.

## 10. Đừng bỏ quên credential và phiên đã tồn tại

Trạng thái cấp quyền hiện tại chỉ là một phần của discovery. Cần phân biệt:

```text
Quyền nhận credential hoặc kích hoạt role
                  |
                  v
Credential / token đã phát hành
                  |
                  v
Phiên hoặc kết nối đang hoạt động
                  |
                  v
Thay đổi quyền hoặc credential mới đã tạo
```

Ví dụ, một tài khoản đã mất quyền đọc bí mật ở vault nhưng trước đó đã lấy một khóa dài hạn. Nếu khóa vẫn có hiệu lực ở hệ thống đích, danh mục quyền hiện tại ở vault chưa phản ánh hết khả năng còn tồn tại.

Các câu hỏi cần ghi nhận gồm:

- Có bằng chứng credential đã được phân phối, sao chép hoặc dùng ở đâu không?
- Có tài khoản hoặc khóa tại đích nằm ngoài cơ chế quản lý dự kiến không?
- Có phiên đang hoạt động với quyền được cấp trước thay đổi không?
- Credential có thể được dùng trực tiếp, bỏ qua broker hoặc cơ chế ghi phiên không?
- Có principal, khóa hoặc thay đổi phân quyền được tạo bởi đặc quyền trước đây cần điều tra tiếp không?

Không khẳng định mọi token đều giữ nguyên quyền tới khi hết hạn. Cách đánh giá quyền, thu hồi và kết thúc phiên phụ thuộc nền tảng. Ghi rõ điều đã xác minh và điều còn cần kiểm tra.

Thông tin về credential và phiên phải được bảo vệ như dữ liệu nhạy cảm. Hồ sơ discovery lưu tham chiếu cần thiết, không chứa mật khẩu, private key hoặc token sử dụng được.

## 11. Ghi một phát hiện để người khác có thể xử lý

Một phát hiện có ích cần đủ thông tin để người khác tái dựng lập luận mà không phải suy đoán từ tên role.

| Trường | Nội dung cần lưu |
| --- | --- |
| Mã phát hiện | Định danh ổn định để theo dõi |
| Chủ thể nguồn | ID, loại danh tính và phạm vi hệ thống |
| Chủ sở hữu | Người hoặc đội chịu trách nhiệm; ghi chưa xác định nếu còn thiếu |
| Khả năng cuối | Hành động và tài nguyên nhạy cảm có thể bị tác động |
| Đường quyền | Từng quan hệ trung gian, hướng quan hệ và scope |
| Điều kiện | Phê duyệt, thời hạn, nguồn, môi trường và ranh giới áp dụng |
| Bằng chứng | Tham chiếu snapshot, policy, audit và mốc thời gian |
| Mức xác minh | Nghi vấn, hỗ trợ bởi cấu hình, đã quan sát hoặc chưa đủ dữ liệu |
| Giới hạn | Nguồn chưa có, điều kiện chưa kiểm tra, phần suy luận còn lại |
| Xử lý tiếp | Chủ trì, ưu tiên, hạn xử lý và cách xác nhận kết quả |

Ví dụ sau là **mô hình hồ sơ minh họa**, không phải cấu hình cho một sản phẩm:

```yaml
finding:
  id: pam-discovery-example-002
  source_identity: directory-A/ops-lan
  owner: automation-operations
  target: production/inventory-database
  capability: indirect-database-administration
  path:
    - relation: member-of
      target: automation-maintainers
    - relation: can-edit-executable-task-content
      target: inventory-maint
    - relation: executes-as
      target: svc-inventory-maint
    - relation: uses-credential-reference
      target: vault/inventory-maint-db
    - relation: authenticates-as
      target: database/inventory-maint-admin
  verification: supported-by-configuration
  evidence_ref: protected-evidence/example-snapshot
  limitations:
    - historical-credential-copies-not-fully-inventoried
  next_action: confirm-need-and-design-reduced-privilege
```

Mỗi quan hệ trong hồ sơ thật cần liên kết được với bằng chứng tương ứng. Nếu dữ liệu được chụp ở các thời điểm khác nhau, cần xem liệu các mắt xích có cùng tồn tại trong khoảng kết luận hay không.

## 12. Ưu tiên và bàn giao phát hiện

Ưu tiên nên dựa trên tác động, khả năng hình thành đường quyền và mức kiểm soát, không chỉ số cạnh trong đồ thị.

Các phát hiện thường cần xem xét sớm gồm:

- Đường tới quyền quản lý IAM, trust, credential hoặc principal khác.
- Khả năng sửa audit, bản sao lưu hoặc cơ chế phục hồi.
- Quyền production thường trực của chủ thể có nguồn truy cập rộng.
- Credential dùng chung hoặc không có chủ sở hữu rõ ràng.
- Đường vòng qua JIT, vault, phê duyệt hoặc cơ chế ghi phiên.
- Khả năng tạo quyền bền vững từ một phiên đặc quyền ngắn hạn.

Độ nghiêm trọng và độ chắc chắn là hai thuộc tính khác nhau. Một đường nghi vấn có tác động rất lớn vẫn cần ưu tiên xác minh, nhưng chưa nên được báo như một đường đã được chứng minh.

Discovery không tự động đồng nghĩa thu hồi ngay. Bàn giao cần gắn với chủ sở hữu công việc, nhu cầu hợp lệ và phụ thuộc vận hành. Nếu có dấu hiệu đang bị lạm dụng, chuyển sang quy trình ứng phó và bảo toàn bằng chứng phù hợp, không chờ đợt review định kỳ.

### Liên hệ các biện pháp PAM

| Phát hiện | Hướng xử lý có thể phù hợp | Kết quả cần xác nhận sau xử lý |
| --- | --- | --- |
| Nhóm gián tiếp có quyền rộng | Sửa quan hệ nhóm hoặc thu hẹp role và scope | Không còn đường tương đương qua nhóm khác |
| Quyền kích hoạt quá rộng | Thu hẹp điều kiện, thời gian và thẩm quyền phê duyệt | Chủ thể không thể tự thay điều kiện để nhận lại quyền |
| Công cụ tác vụ có đầu vào tùy ý | Thiết kế JEA với hành động, tham số và đích được giới hạn | Đầu vào không mở lại khả năng thực thi ngoài nhiệm vụ |
| Bí mật mở đường tới tài khoản mạnh | Giảm quyền tại đích, phân tách danh tính, kiểm soát cấp phát và luân chuyển | Credential cũ và đường sử dụng trực tiếp được xử lý phù hợp |
| Workload dùng chung danh tính rộng | Tách danh tính và giới hạn ai sửa workload | Các workload không tiếp tục chia sẻ khả năng vượt nhu cầu |
| Phiên cũ còn khả năng nhạy cảm | Xử lý phiên theo cơ chế nền tảng | Quyền không còn sử dụng được theo mục tiêu thu hồi |

JIT giảm thời gian quyền hoạt động, nhưng vẫn phải xem ai đủ điều kiện kích hoạt và ai điều khiển bước phê duyệt. Vault kiểm soát credential, nhưng quyền của tài khoản ở đích và quyền sửa workload dùng credential vẫn cần được đánh giá.

## 13. Những sai lầm làm discovery thiếu hoặc thừa phát hiện

### Chỉ tìm role có tên “admin”

Tên role có thể không phản ánh khả năng. Quyền sửa chính sách, thay credential, chỉnh mã chạy đặc quyền hoặc quản lý nhóm có thể tạo tác động lớn dù không mang tên quản trị.

### Xem mọi cạnh đồ thị là một bước nâng quyền chắc chắn

Cạnh có thể thiếu điều kiện, sai scope hoặc chỉ mô tả khả năng đọc. Cần kiểm tra ngữ nghĩa của hành động và ranh giới giữa các bước.

### Chỉ dựa vào log sử dụng

Không có sự kiện có thể do chưa dùng, thiếu log hoặc khoảng quan sát chưa bao phủ chu kỳ công việc. Một quyền chưa thấy dùng vẫn có thể tồn tại và gây rủi ro.

### Dùng snapshot cũ như trạng thái hiện tại

Thành viên nhóm, policy, secret và workload có thể đã thay đổi. Phát hiện cần ghi thời điểm và được xác nhận lại trước khi áp dụng thay đổi quan trọng.

### Đếm trùng nhiều đường tới cùng một khả năng

Một tài khoản có thể tới cùng tài nguyên qua nhiều đường. Nên lưu cả khả năng cuối và từng đường riêng. Xóa một đường chưa đủ nếu đường khác vẫn cho phép cùng khả năng.

### Coi thu hồi một binding là đã hoàn tất

Cần kiểm tra các đường khác, credential đã cấp và phiên đang hoạt động. Hoàn tất discovery của một đường không đồng nghĩa đã hoàn tất việc giảm quyền.

## 14. Thực hành phân tích một tập dữ liệu nhỏ

Giả sử một hệ thống cung cấp các thông tin sau:

1. Người dùng A không có role production trực tiếp.
2. A được sửa mô tả của job X nhưng không được sửa lệnh, tham số hoặc artifact.
3. A có thể thêm thành viên vào nhóm Y.
4. Nhóm Y đủ điều kiện nhận role bảo trì production sau bước phê duyệt của đội độc lập.
5. A được đọc một bí mật cũ; chưa xác minh bí mật còn dùng được tại đích không.
6. Không có log sử dụng role bảo trì trong khoảng quan sát.

### Phân tích mẫu

**Job X:** dữ liệu hiện tại chưa cho thấy A điều khiển nội dung thực thi. Không nên kết luận có đường dùng danh tính của job chỉ từ quyền sửa mô tả. Nếu các thuộc tính khác có tác động, cần bổ sung bằng chứng.

**Nhóm Y:** A có thể thay đổi tập chủ thể đủ điều kiện nhận role. Đây là khả năng nhạy cảm cần ghi nhận. Bước phê duyệt độc lập là điều kiện của đường quyền; chưa đủ cơ sở nói A tự kích hoạt được role production.

**Bí mật cũ:** có một đường nghi vấn qua credential. Cần xác minh tài khoản đích, quyền và trạng thái credential qua quy trình phù hợp, không sao chép bí mật vào hồ sơ.

**Không có log:** chỉ phản ánh khoảng quan sát và độ bao phủ đã biết. Nó không loại bỏ các quan hệ cấp quyền đang tồn tại.

### Hồ sơ cần bổ sung

- Định danh và phạm vi chính xác của A, X, Y và role đích.
- Bằng chứng về khả năng quản lý thành viên nhóm Y.
- Cơ chế phê duyệt và ai có thể thay cơ chế đó.
- Tham chiếu credential, chủ sở hữu và hệ thống sử dụng.
- Khoảng quan sát audit, các loại sự kiện có và chưa có.
- Trạng thái xác minh riêng cho từng đường quyền.

## 15. Khi nào một lượt discovery có thể bàn giao?

Một lượt discovery có thể bàn giao khi phạm vi và kết quả đủ rõ để người nhận tiếp tục xử lý:

- Danh tính và tài nguyên được định danh trong đúng hệ thống.
- Các nguồn dữ liệu đã dùng và phần chưa bao phủ được ghi rõ.
- Mỗi phát hiện nêu khả năng cuối, đường trung gian và điều kiện.
- Bằng chứng có mốc thời gian và mức xác minh tương ứng.
- Chủ sở hữu hoặc trạng thái chưa tìm được chủ sở hữu được thể hiện.
- Không đưa giá trị credential vào hồ sơ.
- Phát hiện được gắn với bước xác nhận nhu cầu, giảm quyền hoặc điều tra tiếp.

Không thể đảm bảo phát hiện mọi quyền ẩn chỉ bằng một lần quét. Cần cập nhật khi thay đổi nhóm, trust, policy, workload, credential hoặc chủ sở hữu. Theo dõi đường quyền mới và đường tái xuất hiện giúp duy trì kết quả sau khi thu hẹp quyền.

Điểm cốt lõi là xem **ai có thể điều khiển điều gì, qua những trung gian nào, trong điều kiện nào và dựa trên bằng chứng nào**. Cách nhìn này giúp danh mục PAM phản ánh gần hơn khả năng thực tế của tài khoản quản trị, tài khoản dịch vụ và hạ tầng nhạy cảm.
