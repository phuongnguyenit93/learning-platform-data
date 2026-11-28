# Temporary privileged account

## 1. Mục tiêu và bối cảnh

Trong chương **Tài khoản đặc quyền**, *temporary privileged account* là tài khoản đặc quyền có vòng đời được giới hạn để phục vụ một nhiệm vụ hoặc khoảng thời gian xác định. Tài khoản có thể được tạo khi cần và được vô hiệu hóa, thu hồi quyền hoặc xóa theo cơ chế đã thiết kế sau khi nhiệm vụ kết thúc.

Đây là một cách giảm số tài khoản quản trị tồn tại lâu dài trên hạ tầng nhạy cảm. Tuy nhiên, tạo tài khoản nhanh chỉ là bước đầu. PAM cần kiểm soát toàn bộ vòng đời: ai yêu cầu, tài khoản thuộc về ai, quyền gì được cấp, credential được phân phối thế nào, hoạt động nào đã diễn ra và việc kết thúc có thực sự chặn truy cập hay chưa.

Sau bài học, bạn có thể:

- Phân biệt tài khoản tạm thời, quyền tạm thời, credential ngắn hạn và phiên có thời hạn.
- Thiết kế một bản cấp tài khoản gắn với nhiệm vụ và người hoặc workload chịu trách nhiệm.
- Áp dụng least privilege, JIT/JEA, vault và kiểm soát phiên vào vòng đời tài khoản.
- Nhận diện lỗi cấp phát, tài khoản bị bỏ quên và quyền còn sót sau thu hồi.
- Lưu bằng chứng mà vẫn dọn dẹp được danh tính không còn nhu cầu.

## 2. Tài khoản đặc quyền tạm thời là gì?

### 2.1. Hai đặc tính phải có

Một tài khoản thuộc nhóm này cần được xem xét theo hai đặc tính:

1. **Có đặc quyền:** nó thực hiện được một hoặc nhiều hành động nhạy cảm trên tài nguyên được giao.
2. **Có vòng đời tạm thời:** mục đích, điều kiện bắt đầu và điều kiện kết thúc được xác định và có cơ chế thực thi.

Ví dụ, một kỹ sư hỗ trợ được cấp tài khoản riêng trên hệ thống đích để chẩn đoán và khởi động lại đúng một dịch vụ trong một cửa sổ bảo trì. Khi công việc hoàn thành hoặc hết hạn, khả năng truy cập phải kết thúc và tài khoản được xử lý theo chính sách.

Tài khoản không trở thành tạm thời chỉ vì tên có chữ “temp”, vì có ngày hết hạn ghi trong ticket hoặc vì người tạo dự định sẽ xóa nó sau này. Cần có người chịu trách nhiệm, cơ chế kết thúc và cách phát hiện khi cơ chế đó thất bại.

### 2.2. Bốn lớp thời hạn khác nhau

| Lớp | Điều được giới hạn | Điều chưa được bảo đảm chỉ từ giới hạn đó |
| --- | --- | --- |
| Tài khoản tạm thời | Vòng đời hoặc khả năng sử dụng của tài khoản | Phiên cũ và quyền phát sinh có thể cần xử lý riêng |
| Quyền tạm thời | Thời gian một vai trò hoặc quyền có hiệu lực | Tài khoản có thể vẫn tồn tại và có quyền từ nguồn khác |
| Credential ngắn hạn | Thời gian phương tiện xác thực được chấp nhận | Tài khoản hoặc quyền không nhất thiết đã bị xóa |
| Phiên có thời hạn | Khoảng tồn tại của một kết nối hoặc phiên | Có thể còn phương tiện để mở phiên mới qua đường khác |

Những lớp này thường phối hợp với nhau nhưng không đồng nhất. Đặc biệt, **mật khẩu hết hạn** có thể chỉ buộc đổi mật khẩu ở một số nền tảng, không đồng nghĩa tài khoản đã bị vô hiệu hóa hoặc mọi truy cập đã kết thúc.

Khi thiết kế, phải gọi đúng tên cơ chế đang dùng và xác định nó được thực thi ở đâu.

### 2.3. Quan hệ với JIT và JEA

JIT giới hạn thời điểm quyền được cấp hoặc kích hoạt. Tài khoản tạm thời là một cách có thể hiện thực JIT, nhưng JIT cũng có thể áp dụng bằng cách kích hoạt quyền trên một tài khoản đã tồn tại.

JEA giới hạn khả năng quản trị đủ cho nhiệm vụ. Một tài khoản chỉ tồn tại 30 phút nhưng có toàn quyền trên mọi máy chủ vẫn chưa đạt mục tiêu giới hạn hành động. Ngược lại, một tài khoản có quyền hẹp vẫn cần được kết thúc khi hết nhiệm vụ.

Các con số thời lượng trong bài chỉ minh họa tình huống. Không có một thời hạn duy nhất phù hợp với mọi công việc và nền tảng.

## 3. Khi nào phù hợp và khi nào nên cân nhắc cách khác?

Những tình huống có thể phù hợp gồm hỗ trợ kỹ thuật có thời hạn, bảo trì theo đợt, một lần chuyển đổi hệ thống hoặc một tác vụ tự động cần danh tính riêng trong thời gian chạy.

Tuy nhiên, không phải nhiệm vụ ngắn nào cũng cần tạo một tài khoản mới. Nếu hệ thống hỗ trợ danh tính cá nhân với quyền kích hoạt theo nhiệm vụ và có thể quy trách nhiệm rõ ràng, cấp quyền tạm thời trên danh tính đó có thể đáp ứng nhu cầu mà không thêm tài khoản tại đích.

| Nhu cầu | Cách tiếp cận cần đánh giá |
| --- | --- |
| Kỹ sư nội bộ cần quyền ngắn hạn | Kích hoạt vai trò trên danh tính cá nhân hoặc cấp tài khoản tạm thời nếu nền tảng yêu cầu |
| Chuyên gia bên ngoài hỗ trợ một lần | Danh tính riêng có thể quy trách nhiệm, phạm vi rõ và cửa sổ sử dụng được kiểm soát |
| Một lần chạy tự động | Danh tính workload phù hợp, có quyền và credential gắn với lần chạy nếu nền tảng hỗ trợ |
| Nhiệm vụ dịch vụ chạy thường xuyên | Danh tính dịch vụ có chủ sở hữu và vòng đời phù hợp; tránh liên tục tạo tài khoản tạm mà không quản lý |
| Phục hồi khi PAM hoặc hệ thống danh tính ngừng hoạt động | Đường khẩn cấp đã được chuẩn bị, không phụ thuộc vào việc phải tạo tài khoản qua chính hệ thống đang hỏng |

Tạo nhiều tài khoản ngắn hạn không tự động làm hệ thống an toàn hơn. Nếu cấp phát và thu hồi không đáng tin cậy, số tài khoản bị bỏ quên có thể tăng cùng số lần tạo.

## 4. Gắn tài khoản với chủ thể, nhiệm vụ và hệ thống đích

### 4.1. Có người chịu trách nhiệm rõ ràng

Với người dùng, tài khoản tại đích cần gắn với một cá nhân đã được nhận diện hoặc một phiên được ràng buộc rõ với cá nhân đó. Dùng một tài khoản tạm chung cho cả nhóm vẫn làm yếu khả năng quy trách nhiệm.

Với workload, phải biết tác vụ nào sử dụng, ai sở hữu tác vụ, nguồn nào được phép yêu cầu cấp và ai có quyền sửa mã hoặc cấu hình thực thi.

Chủ sở hữu tài khoản không chỉ là người tạo nó. Cần có người xác nhận nhu cầu nghiệp vụ và người chịu trách nhiệm xử lý khi cấp hoặc thu hồi lỗi.

### 4.2. Không nhận diện chỉ bằng tên

Tên có thể được tái sử dụng sau khi một tài khoản bị xóa. Tài khoản mới cùng tên có thể là một chủ thể khác trong mô hình định danh của hệ thống.

Mỗi lần cấp nên được liên kết bằng mã yêu cầu, mã lần cấp và định danh tài khoản thực tế tại đích. Khi điều tra, cần phân biệt các thế hệ tài khoản có cùng tên, tránh gán nhầm hành động của một lần cấp cho người của lần khác.

Nếu tài khoản được tạo trên nhiều đích, phải theo dõi từng bản cấp tại từng hệ thống. Thành công trên một máy không chứng minh các máy còn lại đã được tạo đúng hoặc thu hồi xong.

### 4.3. Bản ghi cấp tài khoản tối thiểu

| Trường | Nội dung cần lưu |
| --- | --- |
| Mã yêu cầu và mã lần cấp | Liên kết nhiệm vụ với lần tạo cụ thể |
| Chủ thể nhận quyền | Cá nhân hoặc workload; nguồn xác thực tương ứng |
| Chủ sở hữu và người quyết định | Ai xác nhận nhu cầu, ai chịu trách nhiệm vòng đời |
| Tài nguyên, môi trường | Đích thực tế, ranh giới quản trị và phạm vi |
| Chức năng | Những hành động đặc quyền cần thực hiện |
| Tài khoản tại đích | Định danh thực tế, tên hiển thị và trạng thái |
| Nguồn quyền | Vai trò, nhóm, chính sách hoặc quyền trực tiếp đã gán |
| Thời gian | Điều kiện bắt đầu, thời lượng, hạn kết thúc tuyệt đối |
| Phương tiện xác thực | Loại credential và tham chiếu quản lý, không chứa bí mật |
| Kết thúc | Cách thu hồi, xử lý phiên, tài nguyên liên quan và bằng chứng |
| Lỗi tồn tại | Phần cấp hoặc thu hồi chưa hoàn thành và người xử lý |

## 5. Vòng đời: từ yêu cầu đến dọn dẹp

### 5.1. Yêu cầu và phê duyệt

Yêu cầu cần chỉ rõ công việc, tài nguyên, môi trường, hành động và thời gian. Quyền được phê duyệt phải khớp với nội dung đó.

Tùy chính sách, quyết định có thể do người có thẩm quyền đưa ra hoặc do quy tắc tự động đánh giá một tác vụ đã được cho phép. Không nhất thiết phải có phê duyệt thủ công cho từng lần gọi của workload, nhưng luôn cần kiểm tra danh tính và điều kiện cấp.

Nếu yêu cầu thay đổi đáng kể về đích, quyền hoặc thời gian sau phê duyệt, cần được đánh giá lại. Một phê duyệt cũ không nên trở thành giấy phép tạo bất kỳ tài khoản nào.

### 5.2. Cấp phát trong trạng thái được kiểm soát

Bộ cấp phát xác định đúng đích, tạo tài khoản và gắn quyền theo mẫu đã được cho phép. Khi nền tảng hỗ trợ, có thể chuẩn bị tài khoản trong trạng thái chưa cho phép sử dụng cho đến khi các bước bắt buộc hoàn thành.

Nếu tạo tài khoản thành công nhưng gán quyền hoặc thiết lập thời hạn thất bại, không nên thông báo rằng việc cấp đã hoàn tất. Cần xử lý phần đã tạo, ghi nhận trạng thái lỗi và kiểm tra tài khoản có khả năng đăng nhập ngoài dự kiến hay không.

Việc thử lại cũng cần đối chiếu trạng thái thực tế. Nếu phản hồi bị mất sau khi hệ thống đích đã tạo tài khoản, thử lại thiếu kiểm soát có thể tạo nhiều tài khoản hoặc làm mất dấu đối tượng cần thu hồi.

### 5.3. Kích hoạt và phân phối phương tiện truy cập

Chỉ cho phép sử dụng khi các điều kiện đã được xác nhận: danh tính nhận quyền, phạm vi, thời hạn và đường truy cập. Không gửi mật khẩu hay token qua ticket hoặc đầu ra tác vụ không được bảo vệ.

Vault hoặc broker có thể hỗ trợ cấp và sử dụng credential theo chính sách. Nếu người dùng phải nhận bí mật trực tiếp, cần ghi nhận việc truy xuất và có cơ chế xử lý sau sử dụng phù hợp với loại credential.

Một trạng thái “đã cấp” ở bộ điều phối chưa đủ. Cần xác nhận phù hợp rằng tài khoản và quyền thực sự ở trạng thái được dự định tại hệ thống đích.

### 5.4. Sử dụng và theo dõi

Hoạt động cần gắn với lần cấp, nhiệm vụ và danh tính thực thi. Với phiên tương tác, có thể dùng dữ liệu phiên cùng log tại đích. Với API hoặc tự động hóa, cần log hành động và lần chạy tương ứng.

Trong quá trình dùng, phải ngăn việc mở rộng ngoài phạm vi được duyệt theo khả năng của nền tảng. Nếu tài khoản có thể tự gán thêm quyền hoặc tạo tài khoản khác, thời hạn của nó không tự bảo đảm rằng quyền phát sinh cũng sẽ kết thúc.

### 5.5. Kết thúc và xác nhận thu hồi

Điều kiện kết thúc có thể là hết thời gian, hoàn thành sớm, hủy yêu cầu, tác vụ dừng hoặc sự kiện an ninh. Hệ thống cần ngừng cho phép truy cập mới và xử lý các phương tiện đã cấp.

Các phần cần kiểm tra gồm quyền, trạng thái tài khoản, credential, token, phiên và kết nối. Khả năng thực thi khác nhau giữa các nền tảng; cần nêu rõ phần nào kết thúc tại chỗ, phần nào còn độ trễ và cách phát hiện lỗi.

Không coi việc gửi một lệnh vô hiệu hóa là bằng chứng đã thu hồi thành công. Nếu hệ thống đích không phản hồi hoặc kết quả chưa rõ, yêu cầu vẫn cần được theo dõi.

### 5.6. Dọn dẹp và đóng bản ghi

Sau khi chặn khả năng truy cập, tài khoản có thể được xóa hoặc tiếp tục ở trạng thái không sử dụng được trong một khoảng thời gian theo chính sách và khả năng nền tảng. Việc xóa cần phối hợp với nhu cầu bằng chứng và các tham chiếu còn tồn tại.

Chỉ đóng bản ghi khi kết quả đã được xác nhận và các lỗi còn lại có cách xử lý rõ. Một báo cáo “đã xóa” trong khi còn tài khoản trên một đích khác là trạng thái sai, dù nhiệm vụ nghiệp vụ đã hoàn thành.

## 6. Thời hạn phải được định nghĩa chính xác

### 6.1. Ba thời điểm dễ bị nhầm

Cần phân biệt thời điểm tạo tài khoản, thời điểm tài khoản được phép sử dụng và thời điểm kết thúc. Nếu tạo sớm để chuẩn bị, tài khoản không nên vô tình có thể đăng nhập trước cửa sổ được duyệt.

Một cách tính giới hạn minh họa:

```text
kết_thúc_hiệu_lực = thời_điểm_sớm_nhất_trong(
    lúc_kích_hoạt + thời_lượng_được_duyệt,
    hạn_kết_thúc_tuyệt_đối,
    giới_hạn_theo_chính_sách
)
```

Ví dụ, cửa sổ được duyệt kết thúc lúc 14:45, thời lượng tối đa là 30 phút. Nếu kích hoạt lúc 14:05, thời điểm kết thúc là 14:35. Nếu kích hoạt lúc 14:30, quyền chỉ kéo dài đến 14:45, không tự vượt cửa sổ để đủ 30 phút.

Nếu phê duyệt chỉ có giá trị để bắt đầu trong một khoảng thời gian, cần có thêm điều kiện hạn chót kích hoạt. Yêu cầu đã được duyệt từ lâu không nên dùng để tạo tài khoản vào bất kỳ lúc nào trong tương lai.

### 6.2. Gia hạn là quyết định mới về quyền

Gia hạn cần xác nhận nhiệm vụ còn hợp lệ, phạm vi có thay đổi không và thời lượng mới có nằm trong chính sách không. Cần lưu người hoặc quy tắc ra quyết định cùng lý do.

Tự gia hạn chỉ vì một cửa sổ còn mở hoặc tác vụ chưa báo hoàn thành có thể khiến tài khoản tạm thời trở thành tài khoản hoạt động liên tục. Khi nhiệm vụ thường xuyên vượt thời hạn, nên xem lại thiết kế công việc thay vì kéo dài vô hạn.

### 6.3. Thực thi không được chỉ dựa vào giao diện

Hệ thống thực thi cần có nguồn thời gian tin cậy và cơ chế phù hợp với thời hạn. Đồng hồ trên máy người dùng hoặc một bộ đếm ở trang web không đủ làm căn cứ thu hồi ở đích.

Nếu thu hồi phụ thuộc vào một bộ điều phối trung tâm, cần xác định điều gì xảy ra khi bộ điều phối hoặc đường mạng bị gián đoạn. Có thể cần kết hợp cơ chế hết hạn tại đích với đối chiếu và xử lý sau đó, tùy những gì nền tảng hỗ trợ.

## 8. Least privilege và bảo vệ bộ cấp phát

### 8.1. Cấp đủ cho chức năng, không cấp theo nhãn chung

Nhu cầu “hỗ trợ dịch vụ A” cần được cụ thể hóa. Người hỗ trợ có thể chỉ cần xem tập dữ liệu chẩn đoán được phép và khởi động lại dịch vụ đó, không cần đọc mọi bí mật, thay chính sách truy cập hoặc quản trị các dịch vụ khác.

Cần kiểm tra cả quyền trực tiếp và quyền kế thừa. Một tài khoản mới vẫn có thể nhận quyền rộng do được thêm vào nhóm mặc định không phù hợp hoặc do chính sách đích áp dụng cho một tập tài khoản lớn.

### 8.2. Tài khoản tạm không tự ngăn tạo quyền lâu dài

Nếu tài khoản có quyền tạo người dùng, cấp vai trò hoặc sửa cơ chế xác thực, nó có thể tạo thêm khả năng truy cập sống lâu hơn bản thân tài khoản. Việc xóa tài khoản gốc sẽ không tự thu hồi mọi thay đổi đó.

Do đó, cần giới hạn các hành động quản lý quyền nếu nhiệm vụ không cần. Nếu công việc thực sự yêu cầu thay đổi quyền, phải lưu những đối tượng phát sinh và kiểm tra chúng trong bước kết thúc hoặc rà soát sau sự kiện.

### 8.3. Danh tính của bộ cấp phát cũng là đặc quyền

Bộ cấp phát có khả năng tạo tài khoản hoặc gán vai trò nên chính nó cần được kiểm soát bằng PAM. Không nên để nó chấp nhận tùy ý mọi tên vai trò, đích hoặc tham số từ người yêu cầu.

Cần ràng buộc các mẫu được phép, nguồn yêu cầu, phạm vi đích và quyền của danh tính thực thi. Ai được sửa quy trình cấp phát hoặc mẫu quyền cũng có thể ảnh hưởng đến quyền của các tài khoản được tạo sau này.

Bằng chứng của bộ cấp phát cần giúp đối chiếu yêu cầu với thao tác tại đích, nhưng không được ghi giá trị credential vào log.

## 9. Thu hồi chưa kết thúc nếu còn tài nguyên phụ thuộc

### 9.1. Phiên, token và kết nối

Vô hiệu hóa tài khoản có thể chặn lần xác thực mới nhưng không bảo đảm mọi phiên cũ kết thúc ngay. Một số hệ thống kiểm tra quyền theo yêu cầu, hệ thống khác có thể giữ trạng thái trong token hoặc phiên.

Cần xác định cơ chế cụ thể và các cách kết thúc được hỗ trợ. Nếu không thể thu hồi tức thì, phải nhận diện khoảng thời gian còn hiệu lực và giới hạn nó trong thiết kế, thay vì chỉ ghi “đã hết hạn”.

### 9.2. Tác vụ, dữ liệu và quyền sở hữu

Tài khoản có thể đã tạo tác vụ định kỳ, tệp, đối tượng dữ liệu, khóa hoặc tham chiếu quyền. Xóa tài khoản có thể để lại tài nguyên không có người quản lý hoặc gây lỗi cho công việc còn cần giữ.

Không nên dọn bằng cách xóa hàng loạt mọi thứ gắn với tài khoản mà không phân loại. Cần xác định tài nguyên nào phải thu hồi, tài nguyên nào là kết quả nghiệp vụ hợp lệ cần chuyển quyền sở hữu và tài nguyên nào phải lưu phục vụ điều tra.

Cách xử lý tham chiếu đến tài khoản đã xóa khác nhau giữa các hệ thống. Nếu tái sử dụng tên, cũng phải kiểm tra cơ chế ánh xạ quyền để tránh gắn nhầm đối tượng cũ cho một chủ thể mới.

### 9.3. Giữ bằng chứng độc lập với sự tồn tại của tài khoản

Nhật ký cần lưu đủ định danh và mối liên hệ để vẫn hiểu được hoạt động sau khi tài khoản đã bị xóa. Không nên chỉ dựa vào việc tra tên hiện tại trong danh mục người dùng.

Có thể giữ mã lần cấp, định danh tài khoản tại thời điểm sử dụng, người nhận quyền, đích và dấu thời gian. Việc giữ metadata phục vụ kiểm toán không đòi hỏi giữ credential đã hết nhu cầu trong báo cáo hoặc ticket.

## 10. Ví dụ xuyên suốt: hỗ trợ dịch vụ sản xuất

### 10.1. Bối cảnh

Một chuyên gia hỗ trợ được phép kiểm tra dữ liệu chẩn đoán đã xác định và khởi động lại dịch vụ A trên máy chủ sản xuất. Công việc có cửa sổ kết thúc lúc 14:45, thời lượng sử dụng tối đa 30 phút. Nền tảng đích yêu cầu một tài khoản riêng tại máy để thực hiện các chức năng được giao.

Tài khoản được gắn với chính người hỗ trợ đó, một mã sự cố và một đích cụ thể. Tài khoản không cần quyền quản trị toàn máy hay khả năng tạo tài khoản khác.

### 10.2. Diễn biến mẫu

| Thời điểm hoặc giai đoạn | Trạng thái mong muốn | Bằng chứng cần có |
| --- | --- | --- |
| Phê duyệt | Chưa có khả năng truy cập ngoài phạm vi chuẩn bị | Người nhận, nhiệm vụ, đích, quyền và thời hạn |
| Tạo trước cửa sổ sử dụng | Tài khoản đã được chuẩn bị nhưng chưa cho sử dụng | Định danh tại đích, quyền, trạng thái và kết quả tạo |
| 14:05, kích hoạt | Có quyền đến 14:35 theo giới hạn được duyệt | Xác nhận kích hoạt, phương tiện và mã phiên hoặc lần cấp |
| Trong nhiệm vụ | Chỉ thực hiện các chức năng được giao | Hành động, đích, kết quả và liên kết người thực hiện |
| Hoàn thành sớm hoặc 14:35 | Bắt đầu kết thúc khả năng sử dụng | Lý do kết thúc và các thao tác thu hồi |
| Sau đối chiếu | Tài khoản và phương tiện không còn dùng ngoài chính sách | Kết quả tại đích, xử lý phiên, tài nguyên và bản ghi đóng |

Nếu người hỗ trợ bắt đầu muộn lúc 14:30, giới hạn tuyệt đối 14:45 sẽ rút ngắn lần sử dụng còn 15 phút. Muốn vượt giới hạn phải có quyết định gia hạn hợp lệ, không được âm thầm tính lại cửa sổ.

### 10.3. Logic điều phối minh họa

Mã giả dưới đây mô tả trách nhiệm của bộ điều phối, không phải mã có thể chạy trực tiếp:

```text
cấp_tài_khoản(yêu_cầu):
    kiểm_tra danh_tính, phê_duyệt, phạm_vi và thời_hạn
    đối_chiếu mã_yêu_cầu để tránh tạo_trùng khi thử_lại
    tạo hoặc xác_nhận tài_khoản đúng lần_cấp tại đích
    gán quyền theo mẫu_đã_cho_phép
    thiết_lập giới_hạn và phương_tiện_truy_cập
    xác_nhận trạng_thái_thực_tế
    nếu có lỗi:
        chặn khả_năng_sử_dụng phần đã_tạo nếu có_thể
        ghi phần_lỗi và theo_dõi đến khi xử_lý_xong

kết_thúc(lần_cấp):
    ngừng cho_phép truy_cập_mới theo lần_cấp
    xử_lý quyền, tài_khoản, credential và phiên liên_quan
    đối_chiếu tài_nguyên hoặc quyền phát_sinh
    xác_nhận kết_quả_tại_đích
    nếu chưa_xác_nhận:
        giữ trạng_thái_chờ_xử_lý và cảnh_báo
    nếu hoàn_tất:
        lưu bằng_chứng và đóng lần_cấp
```

Khi yêu cầu bị hủy đồng thời với cấp phát, cần kiểm tra trạng thái trước khi cho sử dụng và xử lý phần đã tạo. Một bản ghi “đã hủy” ở cổng không đủ nếu tài khoản vẫn được tạo xong ở phía đích sau đó.

## 11. Giám sát và xử lý lỗi vòng đời

### 11.1. Các trạng thái cần phân biệt

Có thể dùng các trạng thái như yêu cầu, đã duyệt, đang cấp, đang hoạt động, đang thu hồi, thu hồi lỗi và đã đóng. Tên cụ thể tùy hệ thống, nhưng phải phân biệt được ý định nghiệp vụ với kết quả kỹ thuật.

Đến hạn nghĩa là không còn được phép dùng theo chính sách. Đã thu hồi nghĩa là cơ chế thực thi đã đạt kết quả được xác nhận. Hai sự kiện có thể cách nhau một khoảng thời gian, và khoảng đó cần được theo dõi.

### 11.2. Những trường hợp cần phát hiện

| Tình huống | Ý nghĩa cần kiểm tra |
| --- | --- |
| Tài khoản tồn tại sau hạn nhưng không có bản ghi xử lý | Có thể đã bị bỏ quên hoặc mất đồng bộ kiểm kê |
| Có truy cập mới sau thời hạn | Thu hồi chưa hiệu lực, có đường khác hoặc cấu hình thời gian sai |
| Cấp thành công ở một số đích, lỗi ở đích khác | Cần xử lý trạng thái từng đích, không đóng theo kết quả tổng quát |
| Tài khoản bị hủy nhưng vẫn kích hoạt | Có thể có lỗi phối hợp giữa quyết định và thao tác tại đích |
| Nhiều lần gia hạn nối tiếp | Nhu cầu thực tế hoặc giới hạn đang bị hiểu sai |
| Tài khoản tự tạo thêm quyền, khóa hoặc danh tính | Cần kiểm tra phạm vi thay đổi và khả năng duy trì truy cập |
| Bộ thu hồi lỗi hoặc không chạy | Cần đối chiếu tồn dư và cơ chế xử lý thay thế |

Không nên giải quyết lỗi thu hồi bằng cách tự gia hạn để báo cáo không còn quá hạn. Cần giữ đúng sự kiện hết hạn, ghi phần chưa thu hồi và theo dõi đến khi xử lý.

Khi có dấu hiệu credential bị lộ hoặc tài khoản bị chiếm đoạt, phải xử lý như một sự cố truy cập đặc quyền. Ngoài việc vô hiệu hóa tài khoản, cần xem phiên, quyền và thay đổi đã phát sinh trong thời gian ảnh hưởng.

## 12. Bằng chứng và chỉ số có ích

Một chuỗi bằng chứng đầy đủ cần nối được:

> Nhu cầu → người hoặc workload nhận quyền → phê duyệt → tài khoản tại đích → quyền được cấp → hoạt động → thu hồi và dọn dẹp.

Không ghi mật khẩu, token hoặc khóa vào chuỗi này. Có thể dùng mã định danh credential và tham chiếu quản lý cùng kết quả cấp hoặc thu hồi.

Một số số liệu hữu ích gồm số tài khoản tạm đang hoạt động, số đã quá hạn chưa xác nhận thu hồi, độ trễ kết thúc truy cập, tỷ lệ cấp lỗi một phần, số tài khoản không có chủ sở hữu và số lần gia hạn. Thời gian cấp nhanh là một đặc tính vận hành; nó không thay thế được chất lượng giới hạn quyền và thu hồi.

Cũng cần đối chiếu tồn tại thực tế tại đích với bản ghi điều phối. Nếu chỉ đếm yêu cầu đã đóng, hệ thống có thể bỏ sót tài khoản được tạo nhưng mất dấu do lỗi giữa chừng.

## 13. Sai lầm thường gặp

| Nhầm lẫn | Cách hiểu cần dùng |
| --- | --- |
| Có ngày hết hạn trong ticket là đủ | Thời hạn cần được thực thi và có kết quả xác nhận |
| Tài khoản tạm thì có thể cấp toàn quyền | Giới hạn thời gian vẫn cần đi cùng giới hạn hành động và tài nguyên |
| Mật khẩu hết hạn đồng nghĩa tài khoản ngừng dùng | Cơ chế có thể chỉ yêu cầu đổi mật khẩu; cần kiểm tra nền tảng |
| Xóa tài khoản sẽ xóa mọi quyền và thay đổi nó tạo ra | Quyền hoặc tài nguyên phát sinh có thể còn tồn tại |
| Tài khoản đã bị vô hiệu hóa thì phiên cũ chắc chắn kết thúc | Phiên, token và kết nối có thể có cơ chế riêng |
| Dùng chung một tài khoản tạm cho nhiều người là đủ truy vết | Cần ràng buộc người thực hiện với từng lần sử dụng |
| Có thể tái dùng tên mà không cần mã lần cấp | Tên không đủ phân biệt các thế hệ tài khoản |
| Tác vụ dọn dẹp chạy là đã thu hồi thành công | Phải đối chiếu kết quả thực tế và xử lý phần lỗi |
| Đóng nhiệm vụ nghiệp vụ thì có thể bỏ qua dọn dẹp | Vòng đời truy cập còn phải kết thúc và có bằng chứng |

## 14. Bài tập vận dụng

Một nhà cung cấp được cấp tài khoản quản trị tạm trong 48 giờ để bảo trì. Ngày kết thúc chỉ nằm trong ticket. Mật khẩu được gửi qua một kênh không được quản lý và tài khoản dùng chung cho hai kỹ sư. Sau công việc, bộ phận vận hành xóa tài khoản nhưng không kiểm tra phiên còn hoạt động, tác vụ định kỳ hoặc quyền đã tạo.

Hãy phân tích:

1. Những lớp thời hạn nào chưa được xác định và thực thi?
2. Vì sao không thể quy trách nhiệm đầy đủ chỉ từ tên tài khoản tại đích?
3. Cần thay đổi cách cấp credential và giới hạn quyền như thế nào?
4. Cần kiểm tra những gì trước và sau khi xóa tài khoản?
5. Bản ghi nào phải được giữ để điều tra sau khi tài khoản không còn tồn tại?

**Định hướng trả lời:** cần gắn tài khoản hoặc phiên với từng cá nhân, xác định giới hạn và cơ chế thực thi, quản lý phương tiện xác thực và giảm quyền theo nhiệm vụ. Kết thúc phải xử lý phiên, credential, quyền phát sinh và tài nguyên phụ thuộc. Bằng chứng cần giữ định danh tại đích, mã lần cấp, người nhận quyền, các hành động và kết quả thu hồi, thay vì chỉ giữ tên tài khoản đã bị xóa.

## 15. Ghi nhớ

Temporary privileged account là một đối tượng có vòng đời quản lý, không chỉ là một tài khoản được tạo nhanh và dự định xóa sớm. Tính tạm thời chỉ có ý nghĩa khi điều kiện kết thúc được thực thi và kết quả có thể xác nhận.

Hãy quản lý đồng thời chủ thể nhận quyền, tài khoản tại đích, phạm vi quyền, credential, phiên và tài nguyên phát sinh. Kết hợp least privilege, JIT/JEA, vault và bằng chứng xuyên suốt giúp giảm tài khoản tồn dư và giữ được khả năng kiểm toán, ứng phó sự cố sau khi tài khoản đã kết thúc vòng đời.