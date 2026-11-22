# Quyền POSIX, root squash và xác thực truy cập tệp

## Mục tiêu bài học

Mount thành công một file system OCI File Storage không đồng nghĩa mọi tiến trình trên máy khách đều được đọc hoặc ghi dữ liệu. Quyền truy cập được quyết định qua nhiều lớp: đường mạng, export options, cơ chế xác thực, danh tính UID/GID và quyền trên từng tệp hoặc thư mục.

Bài thuộc chương **File Storage**, module **CLOUD_PROVIDERS_ORACLE**. Nội dung liên hệ IAM, VCN và lưu trữ dùng chung với yêu cầu phân quyền, giám sát và vận hành ứng dụng trên OCI.

Sau bài này, bạn có thể:

- Phân biệt quyền quản lý File Storage trong OCI với quyền đọc/ghi dữ liệu qua NFS.
- Giải thích UID, GID và các bit quyền POSIX trên tệp, thư mục.
- Thiết kế thư mục dùng chung theo nhóm với setgid và chính sách tạo file phù hợp.
- Mô tả tác dụng, giới hạn của root squash và all squash.
- Phân biệt cơ chế AUTH_SYS với các mức bảo vệ của Kerberos khi được cấu hình hỗ trợ.
- Chẩn đoán lỗi truy cập theo danh tính thực của tiến trình thay vì mặc định mở rộng quyền.

Các ví dụ dùng Linux và UID/GID giả định. Khi triển khai, phải đối chiếu khả năng NFS, cơ chế xác thực, export options và các tính năng quyền được OCI File Storage cùng hệ điều hành khách hỗ trợ. Bài tập trung vào quyền POSIX cơ bản, không giả định mọi loại ACL đều được dịch vụ hỗ trợ.

## 1. Một yêu cầu đọc file đi qua những lớp nào?

Một luồng khái niệm:

```text
Tiến trình ứng dụng trên máy khách
  -> kết nối mạng đến mount target
  -> export và điều kiện truy cập tương ứng
  -> cơ chế xác thực và danh tính của yêu cầu
  -> ánh xạ hoặc squash danh tính, nếu áp dụng
  -> quyền trên các thư mục cha và tệp đích
  -> thao tác đọc, ghi hoặc quản lý tệp
```

| Lớp | Câu hỏi quyết định | Ví dụ |
| --- | --- | --- |
| IAM của OCI | Ai được quản lý tài nguyên dịch vụ? | Tạo file system, quản lý export hoặc cấu hình liên quan |
| Mạng VCN | Máy khách có đường giao tiếp đến dịch vụ không? | Route, NSG/security list và firewall |
| Export options | Nguồn truy cập được phép dùng export theo điều kiện nào? | Dải IP, read-only/read-write, cơ chế squash |
| Xác thực NFS | Danh tính nào được dịch vụ tin nhận và bằng cơ chế nào? | AUTH_SYS hoặc Kerberos được hỗ trợ |
| Quyền filesystem | Danh tính hiệu lực có quyền với đường dẫn và thao tác không? | UID/GID, mode và quyền duyệt thư mục |
| Ứng dụng | Người dùng nghiệp vụ có được phép thực hiện thao tác không? | Chỉ chủ hồ sơ được tải tài liệu của mình |

Một IAM user có quyền quản lý file system không tự trở thành owner của mọi file trong đó. Ngược lại, một service account Linux có quyền đọc file chưa chắc được phép sửa export bằng API OCI.

Cũng cần phân biệt danh tính gọi API của instance với danh tính truy cập NFS của tiến trình. Bật instance principal cho ứng dụng không tự thay thế UID/GID hoặc cơ chế xác thực tệp.

## 2. UID và GID mới là dữ liệu định danh quan trọng

### 2.1. Tên tài khoản chỉ là cách hệ điều hành biểu diễn

Trong mô hình quyền UNIX thông thường:

- **UID** định danh user.
- **GID** định danh group.
- Một tiến trình có user/group hiệu lực và có thể có các nhóm bổ sung.
- Mỗi tệp có owner UID, group GID và các bit quyền.

Tên như `appuser` hoặc `finance` được tra từ cơ sở dữ liệu tài khoản của hệ điều hành. Hai máy có thể hiển thị cùng một tên nhưng gán số khác nhau.

| Máy khách | Tên user | UID | Tên group | GID |
| --- | --- | --- | --- | --- |
| A | appuser | 21001 | finance | 3100 |
| B | appuser | 22001 | finance | 3200 |

Nếu dữ liệu được tạo bởi UID 21001, tiến trình UID 22001 không trở thành owner chỉ vì trên máy B cũng có tên `appuser`.

Chiều ngược lại cũng đáng chú ý: UID 21001 có thể mang tên khác trên hai máy nhưng được xem là cùng danh tính số trong mô hình truy cập tương ứng. Vì vậy, đồng nhất tên tài khoản là chưa đủ.

### 2.2. Đồng bộ danh tính giữa các máy

Với ứng dụng chạy nhiều instance, quản lý UID/GID một cách nhất quán bằng image, cấu hình hệ thống hoặc dịch vụ định danh phù hợp. Nếu dùng directory service, phải xác nhận máy khách và cơ chế định danh của dịch vụ được cấu hình đúng; việc dùng một thư mục tài khoản không tự làm mọi tầng xác thực kết nối với nhau.

Kiểm tra cả tiến trình đang chạy. Thêm user vào group không bảo đảm mọi phiên đăng nhập hoặc service đã chạy từ trước lập tức nhận nhóm bổ sung mới. Có thể cần tạo phiên hoặc khởi động lại đúng service theo quy trình vận hành.

Các cơ chế truyền/tra cứu nhóm cũng có giới hạn và điều kiện riêng. Không chỉ kiểm tra group trong file cấu hình rồi kết luận mọi nhóm bổ sung chắc chắn xuất hiện trong yêu cầu NFS.

## 3. Quyền POSIX trên tệp và thư mục

### 3.1. Owner, group và others

Một chuỗi quyền ví dụ:

```text
-rw-r-----  owner=appsvc  group=finance  report.csv
```

Ba nhóm quyền lần lượt áp dụng cho owner, group và others:

| Bit | Giá trị số | Với tệp thông thường | Với thư mục |
| --- | --- | --- | --- |
| `r` | 4 | Đọc nội dung | Liệt kê tên các mục |
| `w` | 2 | Sửa nội dung, theo các điều kiện liên quan | Tạo/xóa/đổi tên mục khi có quyền duyệt phù hợp |
| `x` | 1 | Thực thi theo điều kiện của hệ điều hành | Duyệt/search thư mục để truy cập mục bên trong |

Ví dụ `640` tương ứng:

```text
Owner: 6 = r + w
Group: 4 = r
Others: 0 = không quyền
```

Quyền trên thư mục không được diễn giải giống quyền trên file. Một thư mục có `r` nhưng thiếu `x` có thể cho thấy tên một số mục trong điều kiện phù hợp nhưng không cho phép truy cập nội dung/metadata như người dùng mong đợi.

### 3.2. Cần quyền duyệt trên cả đường dẫn

Để mở `/shared/finance/reports/report.csv`, danh tính cần có quyền duyệt phù hợp trên các thư mục cha, không chỉ quyền đọc file cuối.

Ví dụ file có mode `644`, nhưng thư mục `/shared/finance` có mode `700` và thuộc user khác. Người dùng không thể bỏ qua thư mục đó chỉ vì file cuối cho others đọc.

Khi kiểm tra một lỗi permission denied, cần đọc toàn bộ chuỗi đường dẫn. Sửa mode của file cuối có thể không giải quyết được thiếu quyền `x` ở thư mục cha.

### 3.3. Không cộng dồn ba nhóm quyền một cách tùy ý

Với kiểm tra mode POSIX cơ bản, hệ thống chọn lớp phù hợp với danh tính: owner, group hoặc others. Nếu user là owner nhưng phần owner không cho thao tác, không mặc định lấy thêm quyền từ phần group để bù vào.

Ví dụ một file có mode `040` vẫn không được hiểu là owner chắc chắn đọc được nhờ cũng thuộc group. Cần đánh giá đúng lớp quyền và cơ chế quyền bổ sung nếu môi trường có hỗ trợ.

### 3.4. Quyền xóa phụ thuộc thư mục chứa

Quyền ghi file và quyền xóa tên file là hai chuyện khác nhau. Một user có quyền ghi và duyệt thư mục chứa có thể xóa hoặc đổi tên một mục theo điều kiện filesystem, ngay cả khi file đó không cho user sửa nội dung.

Sticky bit trên thư mục dùng chung giúp hạn chế thao tác xóa/đổi tên theo owner của mục, owner thư mục và danh tính đặc quyền áp dụng. Nó không thay thế quyền đọc/ghi, xác thực hay cơ chế bảo vệ phiên bản dữ liệu.

Vì vậy, nếu yêu cầu là “thành viên đọc được nhưng không được xóa file của nhau”, chỉ đặt file read-only chưa chắc đủ. Cần thiết kế quyền thư mục và cách ứng dụng quản lý vòng đời file.

## 4. Thiết kế thư mục dùng chung theo nhóm

### 4.1. Setgid giúp kế thừa group

Giả sử thư mục `finance` có:

```text
Owner UID: 23001
Group GID: 3100
Mode: 2770
```

Ý nghĩa:

- Owner và thành viên group được đọc, ghi và duyệt thư mục.
- Others không có quyền theo mode này.
- Bit setgid trên thư mục giúp các mục mới kế thừa group của thư mục theo hành vi filesystem được hỗ trợ.

Setgid không tự cấp mọi bit quyền group cho mọi file được tạo. Ứng dụng vẫn quyết định mode khi tạo và chịu các quy tắc liên quan như umask.

### 4.2. Umask và cách ứng dụng tạo file

Trong trường hợp cơ bản không có cơ chế ACL kế thừa can thiệp, nếu chương trình yêu cầu tạo file với mode `666` và tiến trình dùng umask `007`, kết quả thông thường là `660`. Với thư mục yêu cầu `777`, kết quả là `770`.

```text
File thông thường: 666 chịu umask 007 -> 660
Thư mục:          777 chịu umask 007 -> 770
```

Đây là cách loại bỏ bit quyền, không phải phép trừ số thập phân thông thường.

Nếu chương trình chủ động tạo file `600`, setgid và một umask thoáng hơn không tự biến nó thành `660`. Thư viện tạo file tạm, cơ chế ghi file rồi rename và ứng dụng Java có thể đặt quyền riêng; cần thử đúng đường ghi thực tế.

Không đặt quyền thực thi cho mọi file dữ liệu chỉ để group đọc được. File tài liệu cần `r` hoặc `w` phù hợp, không cần `x` như một chương trình.

### 4.3. ACL cần được xác nhận hỗ trợ riêng

POSIX ACL, NFS ACL và mode bits không phải cùng một cơ chế. Không mặc định OCI File Storage, giao thức và client đang dùng hỗ trợ mọi lệnh ACL giống một filesystem cục bộ.

Thiết kế nền trong bài dùng UID/GID, mode, setgid và umask. Nếu muốn dùng ACL hoặc cơ chế quyền bổ sung, cần xác nhận hỗ trợ đầy đủ trước khi xây chính sách phụ thuộc vào nó. Không diễn giải việc `setfacl` thất bại như bằng chứng dữ liệu đã mất hoặc cần cấp quyền IAM lớn hơn.

## 5. Root squash hoạt động thế nào?

### 5.1. Root trên máy khách không mặc nhiên là quản trị viên của file system

Với truy cập NFS theo danh tính UNIX, yêu cầu từ root có thể mang UID 0. Nếu phía server tin nhận danh tính đặc quyền đó mà không có hạn chế phù hợp, quản trị viên máy khách có thể thực hiện nhiều thao tác đối với dữ liệu chia sẻ.

**Root squash** ánh xạ danh tính root từ máy khách sang danh tính anonymous không đặc quyền theo cấu hình export. Các ID liên quan được xử lý theo quy tắc squash của dịch vụ.

Ví dụ giả định:

```text
Tiến trình client gửi yêu cầu với UID 0
  -> export áp dụng root squash
  -> server đánh giá bằng anonymous UID/GID đã cấu hình
  -> kiểm tra quyền tệp/thư mục theo danh tính sau ánh xạ
```

Giá trị anonymous phải được kiểm tra trong cấu hình thực tế, không suy ra chỉ từ tên hiển thị `nobody`. Các máy khách có thể biểu diễn cùng ID bằng tên khác nhau.

### 5.2. Vì sao `sudo` vẫn bị permission denied?

Giả sử anonymous UID/GID không có quyền ghi vào thư mục `2770` của group finance. User ứng dụng thuộc finance ghi được, nhưng một lệnh chạy bằng root có thể bị squash sang anonymous rồi không ghi được.

Đây có thể là hành vi đúng của chính sách, không phải lỗi mount. `sudo` tăng quyền trên máy khách nhưng không tự vượt qua ánh xạ và quyền do server áp dụng.

Tương tự, `chown` từ máy khách có thể bị từ chối vì danh tính sau squash không có quyền quản trị ownership. Không tắt root squash trên mọi nguồn chỉ để một script khởi tạo tiếp tục chạy.

### 5.3. So sánh các lựa chọn squash

OCI export options có các lựa chọn identity squash theo khả năng dịch vụ, với ý nghĩa khái niệm:

| Lựa chọn | Cách xử lý danh tính | Tác động cần hiểu |
| --- | --- | --- |
| Không squash | Giữ danh tính được cơ chế xác thực chấp nhận | Cần tin cậy mạnh vào máy khách và danh tính đặc quyền của nó |
| Root squash | Ánh xạ root sang anonymous | Giảm quyền root từ client nhưng không thay thế xác thực user |
| All squash | Ánh xạ mọi user sang anonymous | Các yêu cầu có thể mất phân biệt theo UID/GID gốc |

Nếu all squash ánh xạ mọi người vào một UID có quyền ghi, mọi người được phép truy cập export có thể hành động với quyền của cùng danh tính đó. Đây không phải cơ chế cô lập từng người dùng.

Anonymous UID/GID cần được chọn sao cho không vô tình trùng với owner hoặc group có đặc quyền nghiệp vụ. Việc gọi một tài khoản là “anonymous” không làm các quyền đã gán cho ID đó tự biến mất.

### 5.4. Giới hạn quan trọng của root squash

Root squash chủ yếu hạn chế yêu cầu mang danh tính root. Trong mô hình AUTH_SYS tin vào danh tính số do máy khách cung cấp, quản trị viên hoặc kẻ chiếm quyền máy khách có thể tạo tiến trình mang UID không phải 0.

Vì vậy, root squash không chứng minh rằng một máy khách bị chiếm quyền không thể giả làm user có UID khác. Nó là một lớp kiểm soát hữu ích, nhưng cần kết hợp phạm vi mạng, quản trị client, xác thực mạnh khi phù hợp và quyền tối thiểu.

Không dùng root squash như một sandbox cho các máy khách không tin cậy nhau mà cùng có quyền gửi yêu cầu theo mô hình danh tính client tự khai báo.

## 6. Export options và quyền filesystem phối hợp ra sao?

### 6.1. Export không thay thế mode bits

Một export có thể cho phép read/write từ một dải IP, nhưng file vẫn có thể từ chối ghi vì quyền POSIX. Ngược lại, file có mode cho phép ghi vẫn không làm một export read-only trở thành read/write.

Có thể diễn giải điều kiện ghi theo mô hình khái niệm:

```text
Đường mạng hợp lệ
  VÀ export cho phép nguồn và thao tác
  VÀ cơ chế xác thực được chấp nhận
  VÀ danh tính sau ánh xạ có quyền với đường dẫn
  -> thao tác mới có thể được chấp nhận
```

Đây là mô hình để kiểm tra từng lớp, không mô tả thứ tự triển khai nội bộ bắt buộc của dịch vụ.

### 6.2. Thiết kế nguồn truy cập có chủ đích

Một phương án minh họa:

| Nhóm client | Nguồn được kiểm soát | Quyền export | Quyền dữ liệu mong muốn |
| --- | --- | --- | --- |
| Ứng dụng xử lý | Nhóm máy ứng dụng đã quản lý | Read/write, squash phù hợp | Chỉ ghi vùng dữ liệu của dịch vụ |
| Nhóm báo cáo | Nhóm máy báo cáo | Read-only | Chỉ đọc dữ liệu được phân quyền |
| Luồng quản trị | Nguồn quản trị hạn chế | Quyền đủ cho tác vụ bảo trì đã được phép | Provision ownership/quyền theo quy trình |

Không để các nguồn chồng lấn với ý định trái ngược mà chưa kiểm tra quy tắc lựa chọn export option. Cũng cần kiểm kê các export hoặc đường truy cập khác dẫn đến cùng dữ liệu: chính sách ở một đường export không tự chứng minh tất cả đường khác đã bị hạn chế tương tự.

Nếu sử dụng điều kiện yêu cầu cổng nguồn đặc quyền, hiểu rằng đây là điều kiện kết nối, không phải xác thực cá nhân. Người có quyền quản trị client có thể điều khiển cổng nguồn; điều kiện đó không thay thế Kerberos hoặc chính sách định danh phù hợp.

### 6.3. Quyền khởi tạo khác quyền chạy thường ngày

Một thư mục gốc mới có thể chưa cho phép service account ứng dụng tạo dữ liệu, trong khi root bị squash. Cần một luồng provision ban đầu có quyền phù hợp để thiết lập owner/group và thư mục cần thiết.

Luồng quản trị này phải được kiểm soát nguồn và thời gian, có người chịu trách nhiệm và trả lại chính sách vận hành sau đó. Không dùng một export rộng với root không bị squash làm trạng thái mặc định chỉ để đơn giản hóa việc `chown`.

Cách khác là thiết kế trước cấu trúc và quyền bằng danh tính quản trị phù hợp với cơ chế xác thực đã chọn. Ứng dụng chạy thường ngày không cần quyền thay đổi ownership của toàn bộ file system.

## 7. Xác thực NFS: AUTH_SYS và Kerberos

### 7.1. AUTH_SYS tin cậy vào danh tính máy khách cung cấp

Với AUTH_SYS, yêu cầu sử dụng thông tin như UID/GID từ phía client. Đây không phải thao tác người dùng nhập password cho mỗi lần đọc file, cũng không phải IAM ký từng thao tác filesystem.

Mô hình này đòi hỏi quản trị client và UID/GID nhất quán, cùng kiểm soát nguồn truy cập. Một hệ thống có mode chặt nhưng cho phép client không tin cậy khai báo danh tính tùy ý vẫn có rủi ro.

### 7.2. Các mức bảo vệ Kerberos

OCI File Storage có cơ chế tích hợp Kerberos theo các điều kiện dịch vụ hỗ trợ. Một triển khai cần cấu hình phía dịch vụ, nguồn định danh, hạ tầng Kerberos và client phù hợp; chỉ thêm một tùy chọn mount không tự tạo ra hệ thống xác thực hoàn chỉnh.

Các security flavor thường được phân biệt như sau:

| Flavor | Mục đích chính | Điều không tự thay thế |
| --- | --- | --- |
| `sys` | Truy cập theo danh tính UNIX mà client cung cấp | Xác thực mạnh từng user bằng Kerberos |
| `krb5` | Xác thực bằng Kerberos | Bảo mật nội dung truyền chỉ nhờ xác thực |
| `krb5i` | Kerberos kèm bảo vệ tính toàn vẹn | Mã hóa nội dung như mức privacy |
| `krb5p` | Kerberos kèm bảo vệ riêng tư/mã hóa lưu lượng theo cơ chế này | Quyền filesystem và kiểm soát ứng dụng |

Chỉ chọn flavor mà export, client và cấu hình dịch vụ thực sự hỗ trợ. Các yêu cầu triển khai có thể gồm DNS, đồng bộ thời gian, principal, ánh xạ danh tính, key material và việc lấy/gia hạn ticket.

Kerberos xác thực danh tính nhưng vẫn cần quyền đọc/ghi phù hợp. Một principal đã xác thực không mặc nhiên được truy cập mọi thư mục. Cũng không mặc định root squash hoặc mapping có cùng tác dụng cho mọi security flavor; kiểm tra cách dịch vụ áp dụng trên cấu hình thực tế.

### 7.3. Service chạy nền cần cơ chế credential phù hợp

Một user đăng nhập tương tác đọc được file không chứng minh service Java chạy nền có credential cần thiết. Service có user, môi trường, session và vòng đời riêng.

Nếu dùng Kerberos, cần thiết kế cách service nhận và duy trì credential theo mô hình được hỗ trợ. Theo dõi tình huống hết hạn ticket, mất kết nối dịch vụ định danh hoặc sai lệch thời gian. Không sao chép credential của người vận hành để làm cơ chế chạy lâu dài cho ứng dụng.

### 7.4. Mã hóa không đồng nghĩa phân quyền

Mã hóa dữ liệu lưu trữ và bảo vệ dữ liệu trên đường truyền là các lớp khác với quyền POSIX. Một kênh truyền được mã hóa có thể vẫn cho phép danh tính đã xác thực đọc một file mà mode cho phép; mã hóa không tự sửa quyền quá rộng.

Ngược lại, mode đúng không ngăn việc quan sát lưu lượng nếu đường truyền không có cơ chế bảo vệ phù hợp. Cần thiết kế cả danh tính, quyền và bảo vệ kênh theo yêu cầu hệ thống.

## 8. Ví dụ: thư mục báo cáo dùng chung cho backend Java

### 8.1. Bối cảnh và danh tính

Hai instance OCI chạy cùng dịch vụ Java và dùng chung thư mục báo cáo. Có một nhóm tạo báo cáo và một nhóm đọc báo cáo. Các ID sau chỉ là giả định của bài:

| Danh tính | UID/GID minh họa | Vai trò |
| --- | --- | --- |
| Service tạo báo cáo | UID 23001, group finance GID 3100 | Tạo và cập nhật nội dung |
| Nhân sự thuộc finance | UID riêng, có group 3100 | Truy cập theo quyền được giao |
| User ngoài finance | UID riêng, không thuộc group 3100 | Không truy cập vùng nội bộ |
| Anonymous sau squash | UID/GID đã chọn riêng trong cấu hình | Không có quyền ghi vùng finance |

Hai instance phải dùng ID nhất quán cho service và group cần chia sẻ. Quyền thư mục cha phải cho phép đúng các danh tính duyệt tới vùng dữ liệu.

### 8.2. Chính sách minh họa

- Thư mục nội bộ thuộc owner dịch vụ và group finance, mode `2770`.
- Service tạo file theo chính sách cho phép group cần thiết truy cập, ví dụ file `660` khi phù hợp.
- Client báo cáo chỉ đọc qua đường export được cấu hình read-only.
- Root squash áp dụng cho các nguồn ứng dụng theo thiết kế.
- Không cấp others quyền chỉ để bù cho UID/GID không nhất quán.

Nếu yêu cầu nhóm đọc và nhóm ghi khác nhau ở mức từng user trên cùng đường truy cập, chỉ một group với mode `2770` không đủ phân biệt. Cần đổi mô hình group/thư mục, đường export hoặc cơ chế quyền được hỗ trợ; không giả định bảng ví dụ đã giải quyết mọi mô hình phân quyền.

### 8.3. Quyền tệp không thay thế phân quyền người dùng web

Mọi request của backend Java có thể thực hiện I/O dưới cùng UID service. File Storage nhìn thấy danh tính service, không tự biết người dùng cuối nào đang đăng nhập vào website.

Nếu người dùng A không được đọc tài liệu của B, ứng dụng phải kiểm tra quyền nghiệp vụ trước khi mở file. Không chỉ dựa vào việc mọi file đều có owner là service để cho phép tải theo một đường dẫn do client gửi.

Tương tự, tên file và đường dẫn từ người dùng phải được xử lý theo mô hình truy cập của ứng dụng. Quyền POSIX giúp giới hạn tiến trình, nhưng không thay thế kiểm tra đối tượng dữ liệu trong ứng dụng.

### 8.4. Container và bước khởi tạo ownership

Trong container, cần đối chiếu UID/GID của tiến trình thực tế với phía NFS. Tên user bên trong image không đủ để chứng minh nó có quyền.

Một init process chạy root để `chown` dữ liệu có thể thất bại do root squash. Các tùy chọn group của nền tảng điều phối cũng không bảo đảm mọi thao tác đổi ownership đều được server chấp nhận. Chuẩn bị quyền bằng quy trình được phép, rồi chạy service với danh tính tối thiểu cần thiết.

## 9. Chẩn đoán lỗi truy cập theo từng lớp

### 9.1. Lệnh đọc trên client Linux

Các lệnh dưới đây dùng để quan sát trong môi trường được phép. Một số công cụ cần cài sẵn; thay đường dẫn và tên user bằng dữ liệu thực tế.

```bash
# Danh tính của phiên hiện tại
id

# Tra danh tính của một tài khoản cụ thể
id appsvc
getent passwd appsvc
getent group finance

# Đối chiếu filesystem và tùy chọn mount
findmnt -T /mnt/team/finance
nfsstat -m

# Xem UID/GID dạng số và mode thực tế
stat -c '%n uid=%u gid=%g mode=%a (%A)' /mnt/team/finance

# Xem quyền từng thành phần của đường dẫn
namei -l /mnt/team/finance/report.csv
```

Lệnh `id` của shell hiện tại không tự chứng minh service đang chạy dùng cùng danh tính. Cần kiểm tra user/group của tiến trình hoặc cấu hình service tương ứng.

Kết quả có tên user đẹp không thay thế việc so số UID/GID. Với môi trường có mapping hoặc xác thực khác, còn phải đối chiếu danh tính được server chấp nhận sau các bước đó.

### 9.2. Trình tự điều tra

1. Xác nhận đúng mount target, export và đường dẫn dữ liệu; tránh kiểm tra một thư mục cục bộ do NFS chưa mount.
2. Kiểm tra đường mạng và policy export của đúng nguồn client.
3. Xác định security flavor và credential thực sự của tiến trình.
4. Xác định UID/GID hoặc danh tính hiệu lực sau mapping/squash.
5. Kiểm tra quyền duyệt mọi thư mục cha và quyền thao tác trên đối tượng đích.
6. Kiểm tra client/export read-only, ownership, mode và những lớp bảo mật hệ điều hành liên quan.
7. Kiểm tra ảnh hưởng của cache danh tính, nhóm bổ sung và tiến trình đã chạy từ trước.
8. Thử lại với đúng danh tính ứng dụng trong môi trường thử nghiệm, không dùng root làm đại diện mặc định.

### 9.3. Bảng triệu chứng

| Triệu chứng | Hướng kiểm tra |
| --- | --- |
| Mount không thành công | Mạng, nguồn export, giao thức/security flavor và điều kiện mount |
| User thường ghi được, `sudo` lại không ghi được | Root squash và anonymous UID/GID |
| Cùng tên user nhưng máy A được, máy B bị từ chối | UID/GID số, nhóm bổ sung, export theo nguồn và credential |
| Đọc được file biết tên nhưng không liệt kê được thư mục | Sự khác nhau giữa quyền `r` và `x` trên thư mục |
| File có quyền đọc nhưng vẫn bị từ chối | Quyền duyệt thư mục cha và danh tính được đánh giá |
| Ghi được file nhưng không xóa được, hoặc ngược lại | Quyền trên thư mục chứa, sticky bit và mode của file |
| `chown` bị từ chối | Quyền danh tính thực sau squash, không mặc định lỗi NFS |
| Client ghi không được dù file cho phép | Export/client read-only, squash, quyền thư mục hoặc chính sách khác |
| Service lỗi sau một thời gian nhưng phiên tương tác vẫn chạy | Credential hết hạn, phiên/group cũ, môi trường service |
| File mới chỉ owner đọc được | Mode chương trình yêu cầu, umask và cách tạo file tạm/rename |

## 10. Kế hoạch thực hành và kiểm chứng chính sách

Dùng thư mục thử riêng và các danh tính đã được quản trị viên chuẩn bị. Các thao tác tạo/sửa/xóa trong bài thực hành phải giới hạn vào dữ liệu thử; phần này không yêu cầu thay đổi quyền của dữ liệu đang phục vụ người dùng.

Lập bảng kiểm chứng:

| Danh tính/tình huống | Phép thử | Kết quả mong muốn theo chính sách minh họa |
| --- | --- | --- |
| Service tạo báo cáo | Tạo rồi đọc lại file thử | Thành công trong vùng được giao |
| Thành viên group đúng | Đọc file có mode/group phù hợp | Thành công |
| User ngoài group | Duyệt thư mục finance | Bị từ chối khi không có quyền khác áp dụng |
| Client read-only | Tạo hoặc sửa file thử | Bị từ chối dù mode file có thể cho ghi |
| Root bị squash | Tạo file trong thư mục anonymous không có quyền | Bị từ chối |
| Hai instance ứng dụng | Đọc file do instance kia tạo | Thành công với ID và quyền nhất quán |
| Tạo file qua luồng ứng dụng thật | Kiểm tra owner/group/mode sau tạo hoặc rename | Đúng chính sách, không chỉ đúng khi tạo bằng shell |
| Service khởi động lại | Truy cập dữ liệu với danh tính/credential mới | Không phụ thuộc phiên đăng nhập cũ của người vận hành |

Nếu một kết quả khác dự kiến, ghi lại nguồn client, security flavor, danh tính hiệu lực, owner/group/mode và export option. Không sửa đồng thời nhiều lớp rồi kết luận một thay đổi riêng lẻ là nguyên nhân.

Về vận hành, theo dõi lỗi quyền trong ứng dụng và các thay đổi cấu hình có ảnh hưởng. Không giả định log quản trị OCI tự chứa đầy đủ mọi lần mở file NFS của từng user; cần thiết kế mức quan sát dữ liệu phù hợp với khả năng của dịch vụ và ứng dụng.

Chính sách đã thử cần có chủ sở hữu và cách tái tạo. Một bộ quyền được sửa tay đúng hôm nay nhưng không được giữ trong cấu hình có thể lệch sau khi thay instance, image hoặc tài khoản service.

## 11. Tự kiểm tra

1. IAM user quản lý được export có mặc nhiên đọc được tất cả file qua NFS không? Vì sao?
2. Hai máy cùng có user `appsvc` nhưng UID khác nhau sẽ gặp vấn đề gì khi dùng quyền theo danh tính số?
3. Vì sao đọc file cần xem cả quyền `x` trên các thư mục cha?
4. User có thể xóa một file mà không có quyền sửa nội dung file đó trong trường hợp nào?
5. Setgid trên thư mục giải quyết việc gì, và vì sao nó chưa bảo đảm file mới có group-write?
6. Tại sao lệnh chạy bằng root có thể bị từ chối trong khi service account lại ghi được?
7. Root squash có ngăn hoàn toàn một quản trị viên client giả làm UID không phải 0 dưới AUTH_SYS không?
8. Khi nào all squash làm mất khả năng phân biệt user bằng quyền UID/GID?
9. `krb5`, `krb5i` và `krb5p` khác nhau ở lớp bảo vệ nào? Chúng có thay thế mode bits không?
10. Vì sao backend Java vẫn phải kiểm tra quyền người dùng cuối dù thư mục NFS đã được phân quyền đúng?

Đầu ra của bài thực hành là một chính sách truy cập có danh tính nhất quán, nguồn client được kiểm soát, quyền tệp đủ dùng và kết quả thử cho cả trường hợp được phép lẫn bị từ chối.
