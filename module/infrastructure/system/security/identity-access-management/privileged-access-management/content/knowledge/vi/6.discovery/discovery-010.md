# Đối soát quyền với directory

Trong quản lý truy cập đặc quyền (Privileged Access Management — PAM), danh sách tài khoản trong directory chưa cho biết đầy đủ ai đang có quyền quản trị trên máy chủ, dịch vụ hoặc tài nguyên cloud. Quyền có thể đến từ nhóm lồng nhau, nhóm cục bộ, role được gán trực tiếp, danh tính dịch vụ hoặc một phiên đã được cấp trước khi cấu hình thay đổi.

**Đối soát quyền với directory** là quá trình liên kết dữ liệu danh tính và quan hệ nhóm với quyền được phê duyệt, cấu hình PAM và quyền quan sát tại hệ thống đích để phát hiện sai lệch. Kết quả phải chỉ ra principal nào có quyền gì, trên đâu, từ nguồn nào và cần xử lý thế nào.

Trong chương **Discovery**, đối soát giúp hoàn thiện kiểm kê đặc quyền trước khi áp dụng least privilege, JIT/JEA, bảo vệ credential, giám sát phiên và lưu bằng chứng phục vụ kiểm toán, ứng phó sự cố. Hoạt động này cần bao quát cả tài khoản quản trị của con người, tài khoản dịch vụ và danh tính dùng cho hạ tầng nhạy cảm.

## 1. Đối soát khác với sao chép thành viên nhóm

Một directory có thể là nguồn đáng tin cậy cho định danh tài khoản và thành viên nhóm, nhưng không mặc nhiên là nguồn duy nhất quyết định quyền hợp lệ. Nhóm tồn tại trong directory không chứng minh mọi thành viên đều đã được phê duyệt làm quản trị viên.

Cần phân biệt ba câu hỏi:

1. **Danh tính là ai và đang ở trạng thái nào?** Ví dụ: tài khoản còn hoạt động, thuộc tổ chức nào, là tài khoản người dùng hay dịch vụ.
2. **Danh tính được phép có quyền gì?** Căn cứ vào vai trò công việc, phê duyệt, phạm vi nhiệm vụ và thời hạn.
3. **Danh tính thực tế có thể làm gì?** Căn cứ vào cấu hình cấp quyền, điều kiện áp dụng và trạng thái thực thi ở hệ thống đích.

Đối soát chỉ có ý nghĩa khi các nguồn này được liên kết đúng. Nếu chỉ so sánh danh sách tài khoản trong PAM với danh sách directory, hệ thống có thể bỏ sót một local administrator chưa từng được đưa vào PAM hoặc một cloud role được gán trực tiếp ngoài nhóm quản trị dự kiến.

| Nguồn | Thông tin thường cung cấp | Điều không nên tự suy ra |
| --- | --- | --- |
| Hồ sơ nhân sự hoặc quản trị danh tính | Trạng thái nhân sự, đơn vị, người quản lý, vòng đời công việc | Quyền thực tế trên mọi tài nguyên |
| Directory | Định danh tài khoản, nhóm, quan hệ thành viên, một số thuộc tính trạng thái | Mọi thành viên nhóm đều có nhu cầu đặc quyền hợp lệ |
| Hệ thống phê duyệt hoặc quản trị quyền | Quyền được chấp thuận, người duyệt, scope, thời hạn, ngoại lệ | Cấu hình ở đích đã khớp quyết định |
| PAM | Ánh xạ tài khoản, vai trò truy cập, kích hoạt JIT, phiên và credential được quản lý | Toàn bộ đường truy cập đều đi qua PAM |
| Hệ thống đích | Local group, ACL, role assignment, policy và phiên đang hoạt động | Principal nào là chủ sở hữu hợp lệ nếu thiếu liên kết danh tính |

Vai trò nguồn chuẩn phải được quy định theo từng thuộc tính. Ví dụ, directory quản lý trạng thái tài khoản, chủ dịch vụ xác nhận nhu cầu của service account, còn hệ thống phê duyệt quản lý thời hạn một quyền quản trị cụ thể.

## 2. Xác định phạm vi đối soát

Trước khi thu thập dữ liệu, cần xác định directory, domain hoặc tenant, nhóm đặc quyền, tập máy chủ, tài khoản dịch vụ, tài nguyên cloud và các loại quyền nằm trong phạm vi.

Một phạm vi ban đầu có thể gồm:

- Nhóm quản trị directory và nhóm được dùng để cấp quyền quản trị máy chủ.
- Tài khoản quản trị riêng của nhân viên và quan hệ với tài khoản làm việc thông thường.
- Nhóm cục bộ hoặc role ở đích có nhận thành viên từ directory.
- Tài khoản dịch vụ, danh tính workload và principal được cấp quyền trực tiếp.
- Quyền đủ điều kiện kích hoạt, quyền JIT đang hoạt động và ngoại lệ khẩn cấp.

Phải ghi lại phần chưa quan sát được: máy chủ không liên lạc được, tenant chưa tích hợp, nhóm ngoài phạm vi đọc hoặc tài nguyên không trả đủ policy. Không có dữ liệu không đồng nghĩa không có quyền.

Collector chỉ nên có quyền đọc cần thiết cho việc đối soát. Không cần cấp quyền quản trị directory, đọc giá trị bí mật hoặc sửa nhóm chỉ để tạo báo cáo. Nếu cần kiểm chứng hành động thực tế tại đích, phải tách phép kiểm chứng đó khỏi việc thu thập cấu hình và thực hiện theo phạm vi được cho phép.

## 3. Liên kết principal bằng định danh ổn định

### 3.1. Tránh ghép chỉ theo tên

Tên đăng nhập, UPN, email và distinguished name có thể thay đổi. Cùng một tên cũng có thể xuất hiện ở hai domain hoặc được dùng lại sau khi một tài khoản bị xóa.

Khóa liên kết nên bao gồm hệ thống nguồn và định danh ổn định phù hợp. Với Active Directory, có thể cần cả `objectGUID` để theo dõi đối tượng directory và SID để đối chiếu các quyền gắn với security principal. Với directory cloud, dùng tenant cùng object ID hoặc định danh tương ứng của nền tảng.

Không coi SID, GUID và object ID ở các hệ thống khác nhau là những giá trị có thể thay thế trực tiếp. Trong môi trường đồng bộ hoặc federation, cần quan hệ ánh xạ được quản lý và có nguồn chứng minh.

| Trường hợp | Cách xử lý |
| --- | --- |
| Đổi tên tài khoản nhưng đối tượng không đổi | Giữ liên kết theo định danh ổn định; cập nhật tên hiển thị |
| Xóa rồi tạo tài khoản mới cùng tên | Xem là principal mới; không tự chuyển quyền cũ theo tên |
| Tài khoản quản trị riêng của cùng nhân viên | Lưu quan hệ chủ sở hữu rõ ràng với hồ sơ con người |
| Principal đến từ domain hoặc tenant khác | Giữ định danh nguồn và kiểm tra quan hệ tin cậy liên quan |
| Chưa phân giải được principal | Đánh dấu chưa xác minh; không tự kết luận đã nghỉ việc hoặc phải xóa |

Trong Active Directory, `SIDHistory` nếu có cũng cần được xét khi phân tích quyền theo cơ chế áp dụng. Đây là dữ liệu có thể ảnh hưởng tới quyền, không phải lý do để ghép tùy ý mọi SID cũ vào một tài khoản mới.

### 3.2. Tách danh tính con người và danh tính máy

Một service account không có hồ sơ nhân sự không nhất thiết là tài khoản mồ côi. Nó có thể thuộc một ứng dụng hợp lệ và cần chủ sở hữu dịch vụ, workload phụ thuộc, mục đích, quyền cùng vòng đời credential.

Tương tự, tài khoản break-glass có thể được thiết kế không dùng hằng ngày. Cần đối chiếu với ngoại lệ và quy trình khẩn cấp đã được phê duyệt, thay vì coi việc không có log gần đây là đủ để thu hồi.

Quan hệ sở hữu nên cho phép một người có nhiều tài khoản đặc quyền và một dịch vụ có nhiều danh tính theo môi trường. Không nên ép mọi tài khoản về một phép nối duy nhất theo email.

## 4. Phân giải quyền qua nhóm và phạm vi

### 4.1. Thành viên trực tiếp chưa phải toàn bộ quan hệ

Ví dụ:

```text
Tài khoản quản trị của kỹ sư
    -> nhóm trực ca
    -> nhóm quản trị ứng dụng
    -> nhóm cục bộ Administrators trên APP-02
    -> quyền quản trị hệ điều hành tại APP-02
```

Một truy vấn chỉ đọc thành viên trực tiếp của nhóm cuối có thể chỉ thấy tên nhóm quản trị ứng dụng. Để xác định người dùng, cần phân giải các lớp thành viên được nền tảng hỗ trợ và giữ lại đường cấp quyền.

Khi phân giải, cần xử lý vòng lặp trong đồ thị, giới hạn phạm vi và ghi rõ cạnh nào chưa đọc được. Không bỏ qua principal chưa phân giải rồi báo tập quyền là đầy đủ.

Với Active Directory, không nên xem thuộc tính `memberOf` đơn thuần là danh sách đầy đủ mọi nhóm hiệu lực. Nó không tự biểu diễn toàn bộ thành viên bắc cầu và không thể hiện primary group theo cùng cách với các quan hệ thành viên thông thường. Cần dùng cơ chế phân giải phù hợp với yêu cầu và phạm vi.

Loại nhóm, phạm vi nhóm, trust và vị trí tài nguyên cũng ảnh hưởng tới khả năng cấp quyền. Một nhóm phân phối hoặc một quan hệ lồng nhau nhìn thấy trong directory không mặc nhiên tạo ra quyền bảo mật tại mọi đích.

### 4.2. Nối nhóm directory với cấu hình ở đích

Thành viên của nhóm `APP-OPS` chỉ trở thành quyền trên máy chủ nếu có cấu hình nối nhóm đó với local group, ACL, role hoặc cơ chế tương ứng. Discovery phải kiểm tra liên kết ở đích, không suy từ tên nhóm.

Quyền cũng có thể được cấp trực tiếp cho người dùng, service account hoặc nhóm cục bộ mà không qua nhóm directory dự kiến. Nếu chỉ đối soát đường chuẩn, các đường cấp quyền ngoài quy trình vẫn có thể tồn tại.

### 4.3. Kiểm kê cả quyền quản lý directory

Directory không chỉ chứa tài khoản mà còn có các quyền quản trị chính nó. Quyền sửa thành viên nhóm đặc quyền, thay đổi thông tin xác thực hoặc sửa ACL của đối tượng nhạy cảm có thể ảnh hưởng đến nhiều hệ thống sử dụng directory.

Vì vậy, cần xem các quyền ủy quyền liên quan trong phạm vi, không chỉ nhóm có tên quen thuộc như quản trị viên. Mức tác động phụ thuộc đối tượng được quản lý, loại quyền và các ràng buộc thực tế.

## 5. Chuẩn hóa quyền trước khi so sánh

Không nên so sánh một danh sách tên nhóm directory với một danh sách tên role ở đích rồi coi các tên khác nhau là sai lệch. Cần chuyển chúng về mô hình mô tả cùng một khả năng quản trị.

Một bản ghi quyền chuẩn hóa có thể gồm:

| Thành phần | Ví dụ nội dung |
| --- | --- |
| Principal | Định danh nguồn và ID tài khoản quản trị |
| Khả năng | Xem trạng thái, khởi động lại dịch vụ, quản lý máy chủ hoặc sửa cấp quyền |
| Tài nguyên | Máy chủ, dịch vụ, vault, project hoặc tập tài sản đã định danh |
| Đường cấp quyền | Nhóm trực tiếp, nhóm lồng nhau, assignment trực tiếp hoặc policy tài nguyên |
| Thời gian | Thời điểm bắt đầu, hết hạn, lịch được phép sử dụng |
| Chế độ | Thường trực, đủ điều kiện kích hoạt hoặc đang kích hoạt JIT |
| Điều kiện | Phê duyệt, endpoint, ngữ cảnh xác thực và các ràng buộc áp dụng |
| Bằng chứng | Nguồn, phiên bản, thời gian quan sát và độ đầy đủ dữ liệu |

Mô hình này là cấu trúc phục vụ đối soát, không thay thế cơ chế đánh giá quyền của hệ điều hành hay cloud. Khi tính quyền hiệu lực, phải xử lý đúng policy, deny, phạm vi kế thừa và điều kiện của nền tảng đích.

Nên giữ riêng ba lớp bằng chứng:

- **Cấu hình cấp quyền:** quan sát được assignment, thành viên nhóm hoặc ACL.
- **Khả năng truy cập được xác minh:** có kết quả từ cơ chế đánh giá phù hợp cho hành động và bối cảnh cụ thể.
- **Hoạt động đã xảy ra:** log ghi nhận principal đã thực hiện hành động trong khoảng quan sát.

Không thấy hoạt động không có nghĩa không có quyền. Ngược lại, một assignment hiện tại cũng không chứng minh mọi hành động đều thực thi được nếu còn điều kiện hoặc giới hạn chưa xét.

## 6. So sánh quyền được phê duyệt và quyền quan sát

### 6.1. Hai tập dữ liệu cần có

**Quyền được phê duyệt** mô tả trạng thái mong muốn: principal nào được phép làm gì, trên đâu, trong điều kiện và thời hạn nào. Nguồn có thể là danh mục vai trò, phê duyệt nhiệm vụ và ngoại lệ còn hiệu lực.

**Quyền quan sát** mô tả trạng thái thu thập được từ directory, PAM và tài nguyên đích. Tập này phải kèm độ mới, độ bao phủ và mức xác minh.

Về mặt khái niệm:

```text
Quyền dư: có khả năng vượt ngoài phạm vi phê duyệt còn hiệu lực.
Quyền thiếu: khả năng cần thiết đã được phê duyệt nhưng chưa hiện diện.
Chưa kết luận: thiếu ánh xạ, thiếu policy, sai khác thời điểm hoặc chưa xét đủ điều kiện.
```

Đây không chỉ là phép trừ hai danh sách. Một quyền rộng ở đích có thể bao trùm nhiều quyền hẹp đã được phê duyệt nhưng vẫn còn phần dư. Một assignment đủ điều kiện kích hoạt cũng không nên bị so với quyền đang hoạt động như hai trạng thái tương đương.

### 6.2. Nhận diện các loại sai lệch

| Loại sai lệch | Ví dụ | Hướng xác minh |
| --- | --- | --- |
| Quyền ngoài phê duyệt | Người dùng có local admin trên máy chủ ngoài tập được giao | Kiểm tra đường cấp quyền và quyết định hợp lệ gần nhất |
| Quyền thiếu | Đã duyệt JIT nhưng endpoint chưa nhận assignment | Kiểm tra kích hoạt, điều kiện, lỗi đồng bộ và trạng thái đích |
| Quyền chưa thu hồi | Quyết định kết thúc đã có nhưng assignment vẫn hiện diện | Đối chiếu thời điểm, cơ chế thu hồi và khả năng truy cập còn lại |
| Principal chưa ánh xạ | ACL chứa SID hoặc object ID không phân giải được | Kiểm tra nguồn định danh, trust, dữ liệu đã xóa và độ bao phủ |
| Chủ sở hữu chưa rõ | Service account mạnh chưa có chủ quản được xác nhận | Xác định workload, đơn vị vận hành và nhu cầu |
| Đường cấp quyền ngoài quy trình | Người dùng được gán trực tiếp thay vì qua nhóm được quản lý | Kiểm tra ngoại lệ và lý do cấp trực tiếp |
| Phạm vi rộng hơn | Nhóm ứng dụng được gán quyền cả môi trường sản xuất | So sánh tài nguyên thực tế với tập được duyệt |
| Sai chế độ cấp quyền | Nhu cầu chỉ được kích hoạt theo JIT nhưng quyền tồn tại thường trực | Kiểm tra quyền thực sự được cấp bởi assignment và điều kiện cưỡng chế |

Không kết luận một principal là mồ côi chỉ vì lần truy vấn hiện tại không phân giải được. Có thể tài khoản đến từ directory khác, collector thiếu quyền đọc hoặc dữ liệu tham chiếu đã cũ. Cần phân biệt **chưa phân giải**, **không có chủ sở hữu xác nhận** và **đã xác minh không còn hợp lệ**.

Một tài khoản đã bị vô hiệu hóa nhưng vẫn nằm trong nhóm mạnh là dấu hiệu cần xử lý cấu hình và vòng đời. Tuy nhiên, cần tách khả năng đăng nhập mới, quyền cấu hình còn lưu và các phiên hoặc credential còn hiệu lực; không diễn giải chúng thành một trạng thái duy nhất.

### 6.3. Ngoại lệ cũng phải có phạm vi và hạn

Tài khoản khẩn cấp, công việc chuyển đổi hoặc quyền hỗ trợ của bên thứ ba có thể có ngoại lệ hợp lệ. Ngoại lệ cần mô tả rõ principal, quyền, tài sản, người chịu trách nhiệm, lý do, thời hạn và biện pháp bù đắp.

Không loại bỏ hoàn toàn đối tượng có ngoại lệ khỏi discovery. Vẫn cần theo dõi quyền và xác minh ngoại lệ chưa hết hạn, chưa bị mở rộng hoặc thay đổi chủ thể.

## 7. Đối soát trong điều kiện dữ liệu thay đổi

### 7.1. Không giả định mọi nguồn là cùng một bản chụp

Directory có thể sao chép qua nhiều máy chủ; đồng bộ lên cloud có độ trễ; PAM và hệ thống đích có lịch cập nhật riêng. Cùng một lần chạy đối soát có thể đọc các trạng thái thuộc những thời điểm khác nhau.

Mỗi nguồn nên có ít nhất thời gian thu thập, trạng thái thành công, phạm vi đã đọc, lỗi và thông tin phiên bản hoặc mốc sự kiện nếu nền tảng cung cấp. Nếu không có phiên bản nhất quán toàn cục, phải ghi nhận giới hạn đó thay vì tạo cảm giác dữ liệu đồng thời tuyệt đối.

Khi thấy một thành viên mới ở directory nhưng chưa xuất hiện ở đích, có thể ghi trạng thái chờ xác minh lan truyền nếu có sự kiện thay đổi hợp lệ và còn trong giới hạn được quy định. Trạng thái này cần mốc kiểm tra lại và ngưỡng chuyển xử lý; không được kéo dài vô hạn.

### 7.2. Xem JIT theo đúng thời điểm

Trước cửa sổ kích hoạt, một người có thể đủ điều kiện dùng role nhưng chưa có quyền hoạt động. Trong cửa sổ, assignment tạm thời có thể hợp lệ. Sau khi hết hạn, cần xác minh việc thu hồi ở điểm thực thi.

Nếu lấy bản chụp phê duyệt lúc 10:00 và bản chụp quyền lúc 10:10 trong khi cửa sổ JIT đã kết thúc lúc 10:05, phép so sánh không xét thời gian có thể kết luận sai. Mỗi phát hiện phải nói rõ nó phản ánh thời điểm nào.

### 7.3. Thu hồi nhóm không đồng nghĩa thu hồi mọi phiên

Nhiều hệ thống ghi quyền hoặc thông tin nhóm vào token, ticket, phiên đăng nhập hay kết nối đã thiết lập. Thay đổi directory có thể ảnh hưởng tới lần xác thực hoặc đánh giá sau nhưng không tự chấm dứt mọi hoạt động hiện có.

Ví dụ, một phiên quản trị đã đăng nhập trước khi thành viên nhóm bị gỡ có thể giữ trạng thái quyền theo cơ chế của nền tảng. Khi xử lý thu hồi khẩn cấp, cần xem cả phiên, token, credential và kết nối liên quan, thay vì chỉ kiểm tra danh sách nhóm đã sạch.

Không phải mọi tác vụ đã khởi chạy đều tự dừng khi quyền khởi tạo hết hiệu lực. Quy trình cần xác định tác vụ nào được hoàn tất, tác vụ nào phải hủy và bằng chứng nào xác nhận hành vi ở đích.

## 8. Một luồng đối soát có thể vận hành

Luồng dưới đây minh họa các bước đánh giá, không phải script áp dụng thay đổi:

```text
1. Chốt phạm vi và các nguồn chịu trách nhiệm cho từng thuộc tính.
2. Thu thập directory, phê duyệt, PAM và cấu hình đích kèm thời gian.
3. Ghi lỗi, phân trang còn thiếu và phạm vi chưa quan sát được.
4. Liên kết principal bằng định danh ổn định; giữ các trường hợp chưa rõ.
5. Phân giải đường nhóm, assignment, trust và phạm vi tài nguyên.
6. Chuẩn hóa khả năng quản trị, chế độ cấp quyền và thời hạn.
7. So sánh theo ngữ nghĩa nền tảng, xét ngoại lệ và thời điểm.
8. Tạo phát hiện kèm bằng chứng, độ tin cậy và người chịu trách nhiệm.
9. Xác minh lại nguồn hiện hành trước mọi quyết định thay đổi.
10. Sau xử lý, thu thập lại và kiểm tra tác động còn tồn tại.
```

Nếu một thay đổi thu hồi vừa xảy ra trong khi đối soát đang chạy, không dùng bản phê duyệt cũ để tự cấp lại quyền. Cần kiểm tra quyết định mới nhất, phiên bản và lý do thay đổi. Đối soát phát hiện sự khác biệt; việc sửa phải tuân theo ý định quản trị hiện hành.

## 9. Ví dụ: quyền JEA đúng nhưng vẫn còn local admin

Giả sử tài khoản quản trị `minh-admin` được ánh xạ tới một nhân viên đang hoạt động. Nhiệm vụ hiện tại chỉ cho phép xem trạng thái và khởi động lại dịch vụ thanh toán trên `APP-02`, trong cửa sổ JIT từ 14:00 đến 14:30.

Đợt đối soát lúc 14:10 thu được:

| Nguồn | Dữ liệu quan sát |
| --- | --- |
| Directory | Tài khoản còn hoạt động, thuộc nhóm phục vụ truy cập endpoint ứng dụng |
| Phê duyệt | Chỉ hai hành động trên dịch vụ được giao tại `APP-02`, hết hạn 14:30 |
| PAM | Có kích hoạt và phiên tương ứng trên `APP-02` |
| Endpoint `APP-02` | Vai trò JEA công bố đúng các chức năng được duyệt |
| Máy chủ `APP-03` | Tài khoản được thêm trực tiếp vào nhóm cục bộ `Administrators` |

Nếu chỉ so sánh nhóm directory với vai trò PAM, kết quả có thể trông hợp lệ. Khi đối soát thêm cấu hình đích, quyền quản trị trực tiếp trên `APP-03` là một đường ngoài phạm vi phê duyệt đã thu thập.

Phát hiện cần ghi rõ:

- Principal được liên kết bằng định danh nào, không chỉ bằng tên `minh-admin`.
- Cấu hình local group trên `APP-03` là nguồn của quyền dư.
- Quyết định hiện hành chỉ bao phủ `APP-02` và các hành động dịch vụ cụ thể.
- Có hay không ngoại lệ hợp lệ cho `APP-03`; dữ liệu đã đủ tới mức nào.
- Việc thực thi hoặc đăng nhập tại `APP-03` đã được xác minh hay mới xác nhận cấu hình cấp quyền.

Giả sử tới 14:35 nhóm phục vụ kích hoạt đã được gỡ khỏi directory nhưng phiên trên `APP-02` vẫn còn kết nối. Chỉ riêng kết nối còn mở chưa chứng minh người dùng vẫn thực hiện được hành động đặc quyền, nhưng là lý do để xác minh cơ chế hết hạn của endpoint. Không đánh dấu thu hồi hoàn tất chỉ vì directory đã đúng.

Khi xử lý, cần xem riêng đường local admin tại `APP-03` và vòng đời phiên tại `APP-02`. Hai đường này có nguồn quyền, chủ quản và cách khắc phục khác nhau.

## 10. Ưu tiên và xử lý sai lệch

### 10.1. Ưu tiên theo tác động và độ tin cậy

Những trường hợp cần ưu tiên thường gồm quyền trên hệ thống sản xuất nhạy cảm, khả năng sửa cấp quyền, tài khoản đã mất điều kiện sử dụng nhưng còn đường truy cập, hoặc quyền không qua cơ chế PAM dự kiến.

Độ tin cậy phải tách khỏi mức tác động. Một principal chưa phân giải nhưng có cấu hình quản trị toàn bộ hệ thống có thể cần xác minh gấp, dù chưa đủ bằng chứng kết luận chủ thể không hợp lệ.

| Phát hiện | Trọng tâm xử lý |
| --- | --- |
| Quyền mạnh ngoài phê duyệt trên tài sản nhạy cảm | Xác minh nhanh trạng thái hiện hành và phối hợp chủ tài sản |
| Tài khoản bị vô hiệu hóa nhưng còn assignment hoặc phiên liên quan | Kiểm tra cả cấu hình, phiên và credential còn sử dụng được |
| Nhóm chưa phân giải thành viên | Hoàn thiện dữ liệu, đánh giá tác động tiềm năng |
| Thiếu quyền đã duyệt cho tác vụ vận hành | Xác minh nguyên nhân và quyết định hiện hành trước khi cấp bổ sung |
| Sai khác còn trong giới hạn lan truyền hợp lệ | Theo dõi có hạn, kiểm tra lại và chuyển xử lý nếu quá ngưỡng |

### 10.2. Không biến đối soát thành tự động cấp hoặc xóa quyền

Trước khi sửa một sai lệch, cần xác minh bằng chứng mới nhất, nhu cầu hợp lệ, ngoại lệ và phụ thuộc dịch vụ. Với quyền được cho là thiếu, phải kiểm tra xem việc gỡ quyền có phải quyết định an ninh mới hơn hay không.

Đối với service account, gỡ nhóm hoặc đổi credential có thể ảnh hưởng nhiều dịch vụ. Cần biết ứng dụng nào sử dụng, cách cập nhật phụ thuộc, cách xác nhận phục hồi và phương án xử lý khi có lỗi.

Nếu nghi ngờ credential đã bị lộ, việc sửa thành viên nhóm có thể chưa đủ. Quy trình ứng phó cần xem quyền, bí mật, token và phiên theo cơ chế thực tế, đồng thời giữ bằng chứng. Luân chuyển credential phải đi cùng cập nhật nơi sử dụng hợp lệ để tránh tạo gián đoạn không kiểm soát.

Sau xử lý, thu thập lại đường quyền liên quan và kiểm tra những đường thay thế. Loại bỏ một assignment trực tiếp không giải quyết được vấn đề nếu principal vẫn nhận cùng quyền qua nhóm khác.

### 10.3. Tiêu chí đóng phát hiện

Một phát hiện chỉ nên được đóng khi có quyết định rõ ràng và bằng chứng tương ứng. Ví dụ:

- Quyền không hợp lệ đã bị gỡ ở nguồn cấp quyền và được xác minh tại đích theo yêu cầu.
- Phiên hoặc credential cần thu hồi đã được xử lý, hoặc phần tồn tại còn lại được đánh giá và quản lý rõ ràng.
- Quyền hợp lệ đã được xác nhận bằng phê duyệt hiện hành với scope và thời hạn phù hợp.
- Ngoại lệ được chấp thuận bởi đúng thẩm quyền và có mốc rà soát.
- Phát hiện do dữ liệu thiếu đã được phân giải với bằng chứng, không chỉ bị bỏ qua.

Đổi trạng thái trên báo cáo mà không kiểm tra lại thực tế không chứng minh sai lệch đã được xử lý.

## 11. Lưu bằng chứng đối soát

Mỗi phát hiện cần có đủ dữ liệu để một người khác tái dựng kết luận mà không phải dựa vào trí nhớ của người chạy collector.

Nên lưu định danh principal và chủ sở hữu, scope, quyền được duyệt, quyền quan sát, đường cấp quyền, trạng thái kích hoạt và các mốc thời gian liên quan. Kèm theo đó là nguồn dữ liệu, phiên bản hoặc bản chụp policy, phạm vi thu thập thành công và những điều kiện chưa kiểm tra được.

Quá trình xử lý cũng cần ghi người đánh giá, quyết định, yêu cầu thay đổi, kết quả tại đích và thời điểm xác minh lại. Nếu có thay đổi trong khi đang xử lý, giữ được liên kết giữa các phiên bản để tránh dùng bằng chứng cũ cho trạng thái mới.

Không đưa mật khẩu, token hoặc giá trị bí mật vào hồ sơ đối soát. Dữ liệu danh tính, nhóm và bản đồ đặc quyền vẫn cần được bảo vệ vì có thể chỉ ra đường truy cập tới hệ thống quan trọng. Quyền sửa hoặc xóa bằng chứng nên được tách khỏi vai trò đang được kiểm tra.

## 12. Tiêu chí kiểm chứng và duy trì đối soát

Khi xây dựng quy trình, cần kiểm chứng các tình huống có kết quả dự kiến rõ ràng. Bảng dưới đây là gợi ý cho môi trường thử nghiệm hoặc bộ dữ liệu được quản lý, không phải kết quả kiểm thử của một triển khai cụ thể.

| Tình huống | Kết quả cần đạt |
| --- | --- |
| Tài khoản đổi tên nhưng ID không đổi | Giữ đúng ánh xạ và lịch sử |
| Tài khoản mới dùng lại tên cũ | Không kế thừa liên kết hoặc phê duyệt theo tên |
| Quyền đến từ nhóm lồng nhau hoặc nhóm cục bộ | Nối được đầy đủ đường cấp quyền hoặc chỉ rõ phần còn thiếu |
| Có primary group, trust hoặc principal từ nguồn khác | Không bỏ sót chỉ vì một truy vấn thành viên đơn giản |
| Service account không có hồ sơ nhân sự | Phân loại theo danh tính máy và chủ dịch vụ |
| Quyền đủ điều kiện nhưng chưa kích hoạt | Không coi như quyền JIT đang hoạt động |
| Phiên được mở trước thời điểm thu hồi | Xem xét khả năng tồn tại sau thay đổi directory |
| Collector gặp lỗi hoặc không lấy hết các trang dữ liệu | Ghi nhận kết quả không đầy đủ, không tự báo hết quyền |
| Dữ liệu phê duyệt cũ mâu thuẫn với thu hồi mới | Không tự cấp lại quyền bằng trạng thái cũ |
| Một đường quyền bị gỡ nhưng đường khác còn tồn tại | Chưa đóng phát hiện nếu phần vượt phạm vi vẫn còn |

Nên kết hợp đối soát định kỳ với sự kiện thay đổi tài khoản, nhóm, assignment và phê duyệt theo khả năng của hệ thống. Cần có lượt đối soát đầy đủ để phát hiện sự kiện bị bỏ lỡ hoặc ánh xạ sai tích lũy.

Các chỉ số hữu ích gồm tỷ lệ tài sản được quan sát thành công, số principal chưa phân giải, tuổi dữ liệu, số quyền đặc biệt chưa có chủ quản, thời gian từ quyết định thu hồi đến xác minh tại đích và tỷ lệ sai lệch lặp lại sau xử lý.

Đối soát có giá trị khi liên kết được danh tính, ý định cấp quyền và khả năng truy cập thực tế trong đúng phạm vi thời gian. Directory là một nguồn quan trọng của bản đồ đó; PAM cần nối nó với hệ thống phê duyệt, cấu hình đích, credential và phiên để quản lý đặc quyền xuyên suốt vòng đời.
