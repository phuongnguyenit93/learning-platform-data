# Vì sao tài khoản đặc quyền có rủi ro cao

## Mục tiêu bài học

Trong chương **Khái niệm PAM**, bài này giải thích vì sao quyền quản trị làm tăng hậu quả của một sai sót hoặc một lần bị chiếm quyền, và vì sao chỉ quản lý mật khẩu chưa đủ để kiểm soát rủi ro.

Sau bài học, bạn có thể:

- Nhận diện đặc quyền dựa trên khả năng thực tế của danh tính, kể cả khi tài khoản không mang tên `admin` hay `root`.
- Phân tích rủi ro theo phạm vi tác động, thời gian quyền tồn tại, khả năng làm lộ quyền và chất lượng bằng chứng.
- Giải thích vai trò của kiểm kê quyền, least privilege, JIT/JEA, vault, luân chuyển credential và giám sát phiên.
- Chọn câu hỏi và biện pháp kiểm soát phù hợp cho tài khoản con người, dịch vụ và hạ tầng nhạy cảm.

Phạm vi này thuộc **quản lý truy cập đặc quyền — Privileged Access Management (PAM)**: kiểm soát việc cấp, sử dụng, giám sát và thu hồi quyền có khả năng gây ảnh hưởng lớn đến hệ thống.

## 1. Đặc quyền là khả năng vượt qua một ranh giới kiểm soát

Một tài khoản có đặc quyền khi nó có thể thực hiện thao tác ảnh hưởng đáng kể đến tính bí mật, toàn vẹn hoặc sẵn sàng của hệ thống, dữ liệu hay cơ chế bảo vệ.

Những khả năng điển hình gồm:

- Đọc dữ liệu nhạy cảm ngoài phạm vi công việc thông thường.
- Thay đổi cấu hình máy chủ, ứng dụng, cơ sở dữ liệu hoặc hạ tầng.
- Tạo danh tính mới, cấp quyền hoặc thay đổi chính sách truy cập.
- Đọc, phát hành hoặc luân chuyển bí mật dùng để truy cập hệ thống khác.
- Vô hiệu hóa cơ chế bảo vệ, sửa chính sách ghi log hoặc thay đổi nơi lưu bằng chứng.
- Xóa tài nguyên, phục hồi bản sao lưu hoặc thay đổi chuỗi triển khai phần mềm.

Tên tài khoản không quyết định mức rủi ro. Một danh tính tên `reporting-job` nhưng có thể xuất toàn bộ dữ liệu khách hàng vẫn cần được coi là có đặc quyền đối với dữ liệu đó. Một tài khoản chỉ được sửa pipeline nhưng có thể đưa mã vào production có thể tạo ra tác động quản trị gián tiếp.

Cần phân biệt hai dạng:

| Dạng đặc quyền | Khả năng | Ví dụ |
| --- | --- | --- |
| Trực tiếp | Được phép tự thực hiện thao tác nhạy cảm | Quản trị viên sửa chính sách IAM hoặc quản trị cơ sở dữ liệu xuất bảng khách hàng |
| Gián tiếp | Kiểm soát thành phần được danh tính mạnh hơn tin cậy hoặc sử dụng | Người sửa pipeline có thể làm thay đổi tác vụ chạy bằng danh tính triển khai production |

Đặc quyền luôn gắn với **tài nguyên và thao tác cụ thể**. Quyền quản trị một máy thử nghiệm không đồng nghĩa quyền quản trị toàn bộ tổ chức; quyền đọc một kho bí mật dùng chung có thể có phạm vi tác động lớn hơn tên vai trò gợi ra.

## 2. Vì sao cùng một sự cố nhưng hậu quả khác nhau?

Giả sử hai tài khoản đều bị lộ một credential:

- Tài khoản thứ nhất chỉ xem được lịch làm việc của một nhóm.
- Tài khoản thứ hai có thể cấp vai trò quản trị, truy cập kho bí mật và thay đổi cấu hình production.

Cơ chế lộ credential có thể giống nhau, nhưng tập hành động mà người chiếm quyền có thể thực hiện rất khác nhau. Với tài khoản thứ hai, một lần truy cập trái phép có thể mở ra nhiều hệ thống, nhiều loại dữ liệu và nhiều cách duy trì quyền.

Có thể dùng khung suy nghĩ định tính:

> Rủi ro phụ thuộc vào khả năng quyền bị sử dụng sai và mức tác động nếu điều đó xảy ra.

Đây không phải công thức tính điểm đã chuẩn hóa. Khi phân tích một tài khoản cụ thể, cần làm rõ ít nhất bốn câu hỏi:

1. Danh tính này thực sự làm được gì, trên những tài nguyên nào?
2. Ai hoặc thành phần nào có thể sử dụng danh tính đó?
3. Quyền và phương tiện truy cập có hiệu lực trong bao lâu?
4. Có thể phát hiện, quy trách nhiệm và phục hồi khi quyền bị lạm dụng không?

Tài khoản đặc quyền không nhất thiết dễ bị tấn công hơn mọi tài khoản thường. Rủi ro cao xuất hiện khi quyền có hậu quả lớn kết hợp với đường tiếp cận yếu, thời gian phơi lộ dài hoặc khả năng kiểm soát kém.

## 3. Những yếu tố làm tăng rủi ro của tài khoản đặc quyền

### 3.1. Một thao tác có thể ảnh hưởng diện rộng

**Phạm vi tác động (blast radius)** là tập tài nguyên, dữ liệu và hoạt động có thể bị ảnh hưởng khi một danh tính bị sử dụng sai.

Một quyền được gán ở cấp tổ chức, tài khoản cloud hoặc toàn cụm thường có phạm vi lớn hơn quyền chỉ áp dụng cho một tài nguyên. Quyền xóa bản sao lưu hoặc thay đổi cơ chế khôi phục còn có thể làm tăng thời gian gián đoạn sau sự cố.

Cần xem cả tác động trực tiếp lẫn tác động lan truyền. Ví dụ, thay đổi một chính sách truy cập dùng chung có thể ảnh hưởng nhiều ứng dụng dù danh tính không trực tiếp đăng nhập vào từng ứng dụng đó.

### 3.2. Có thể tạo thêm quyền hoặc duy trì quyền

Quyền quản trị danh tính có thể cho phép tạo tài khoản, thêm thành viên vào nhóm mạnh hơn hoặc sửa quan hệ tin cậy. Khi đó, đổi mật khẩu của tài khoản bị lộ chưa chắc đã kết thúc sự cố: quyền mới, token còn hiệu lực hoặc thay đổi cấu hình đã tạo ra có thể tiếp tục tồn tại.

Các quyền có khả năng **cấp lại quyền** cần được kiểm tra riêng. Chúng có thể làm cho phạm vi đặc quyền thực tế lớn hơn danh sách vai trò gán trực tiếp ban đầu.

### 3.3. Credential có thể xuất hiện ở nhiều nơi

Mật khẩu không phải phương tiện truy cập duy nhất. Những vật mang quyền hoặc phương tiện để nhận quyền có thể gồm:

- Mật khẩu, khóa SSH và khóa riêng.
- API key, access token, refresh token hoặc thông tin xác thực của ứng dụng.
- Chứng thư và khóa riêng dùng để xác thực máy hoặc dịch vụ.
- Phiên đăng nhập đang có hiệu lực và cookie phiên có giá trị xác thực.

Mỗi loại có cơ chế hết hạn, thu hồi và ràng buộc sử dụng khác nhau. Không nên giả định rằng đổi một mật khẩu sẽ vô hiệu hóa mọi khóa, token hoặc phiên liên quan.

Credential tĩnh còn có thể bị sao chép vào cấu hình triển khai, biến môi trường, máy cá nhân, bản sao lưu hoặc đầu ra của tác vụ tự động. Càng nhiều bản sao ngoài kiểm soát, việc xác định ai đang giữ quyền càng khó.

### 3.4. Quyền thường trực kéo dài cửa sổ bị lạm dụng

Một người chỉ cần sửa cấu hình production trong 30 phút có thể vẫn giữ quyền quản trị nhiều tháng nếu không có cơ chế thu hồi theo thời gian.

Khoảng thời gian không thực sự cần quyền vẫn tạo ra cơ hội cho:

- Credential bị đánh cắp rồi sử dụng sau đó.
- Tài khoản bị chiếm qua một hệ thống phụ thuộc.
- Thao tác nhầm môi trường trong công việc hằng ngày.
- Người đã chuyển vị trí vẫn giữ quyền cũ.

Giảm quyền thường trực giúp thu hẹp cửa sổ này. Tuy nhiên, quyền tạm thời vẫn nguy hiểm trong lúc có hiệu lực nếu phạm vi quá rộng hoặc điều kiện cấp quyền yếu.

### 3.5. Tài khoản dùng chung làm mờ trách nhiệm

Khi nhiều người cùng biết mật khẩu của một tài khoản quản trị, log thường chỉ cho biết tài khoản kỹ thuật đã hành động. Việc xác định người thao tác thực tế phụ thuộc vào bằng chứng bổ sung, có thể không đầy đủ.

Khó khăn này ảnh hưởng cả kiểm toán lẫn ứng phó sự cố:

- Khó phân biệt thao tác hợp lệ với hành vi sử dụng credential bị đánh cắp.
- Khó thu hồi quyền của một người mà không ảnh hưởng người còn lại.
- Khó xác nhận ai đã phê duyệt và vì sao quyền được sử dụng.
- Dễ phát sinh các bản sao credential không được quản lý.

Một số hệ thống cũ vẫn cần tài khoản kỹ thuật dùng chung ở phía đích. Khi đó, PAM có thể ánh xạ mỗi lượt sử dụng về người yêu cầu đã xác thực, kiểm soát phiên và ghi bằng chứng. Cơ chế này chỉ hiệu quả nếu các đường truy cập trực tiếp ngoài quy trình cũng được kiểm soát.

### 3.6. Có thể làm suy yếu chính cơ chế giám sát

Một danh tính vừa quản trị hệ thống vừa sửa được log hoặc cấu hình thu thập log có thể làm giảm khả năng phát hiện và điều tra.

Vì vậy, không chỉ hỏi “có ghi log không”, mà cần hỏi:

- Ai có thể tắt nguồn log hoặc thay đổi nơi chuyển log?
- Ai có thể xóa bằng chứng đã lưu?
- Bằng chứng có được lưu ở miền quản trị tách biệt phù hợp không?
- Việc thay đổi cấu hình giám sát có tạo cảnh báo hay không?

Không có loại log nào tự nó đảm bảo quy trách nhiệm đầy đủ. Bằng chứng cần đủ ngữ cảnh, được bảo vệ và được đối chiếu giữa các nguồn liên quan.

### 3.7. Sai sót hợp lệ cũng có thể gây sự cố lớn

Rủi ro đặc quyền không chỉ đến từ người tấn công hay người nội bộ cố ý làm sai. Người vận hành hợp lệ có thể:

- Chọn nhầm môi trường production thay vì môi trường kiểm thử.
- Chạy thao tác hàng loạt trên phạm vi quá rộng.
- Cấp nhầm vai trò cho một nhóm đông người.
- Luân chuyển credential nhưng bỏ sót ứng dụng phụ thuộc.
- Thay đổi chính sách khiến đội vận hành mất quyền khôi phục.

Giới hạn quyền, tách môi trường, xem trước thay đổi và kiểm tra điều kiện thao tác giúp giảm hậu quả của sai sót. Ghi hình phiên sau sự cố không thay thế được các kiểm soát phòng ngừa này.

## 4. Những danh tính nào cần được đưa vào phạm vi PAM?

Chỉ kiểm kê tài khoản quản trị của con người sẽ bỏ sót nhiều đường sử dụng đặc quyền.

| Nhóm danh tính | Nguồn rủi ro thường gặp | Câu hỏi cần trả lời |
| --- | --- | --- |
| Quản trị viên, người vận hành | Dùng tài khoản mạnh cho hoạt động hằng ngày; quyền rộng hơn nhiệm vụ | Có tách tài khoản thường và tài khoản quản trị không? Có thể cấp quyền theo tác vụ không? |
| Tài khoản dịch vụ, tác vụ định kỳ | Credential dài hạn; quyền dư; chủ sở hữu không rõ | Dịch vụ thực sự cần thao tác nào? Ai chịu trách nhiệm và thu hồi bằng cách nào? |
| Danh tính workload, pipeline triển khai | Quan hệ tin cậy quá rộng; thay đổi mã hoặc pipeline dẫn đến sử dụng quyền production | Ai sửa được workflow? Quyền nhận được có bị giới hạn theo môi trường và ngữ cảnh chạy không? |
| Quản trị IAM, cloud, nền tảng điều phối | Có thể sửa chính sách, cấp quyền hoặc điều khiển nhiều tài nguyên | Có quyền nào cho phép tự nâng quyền hay mở rộng phạm vi sang hệ thống khác không? |
| Quản trị vault, bản sao lưu, công cụ bảo mật | Có thể tiếp cận bí mật hoặc vô hiệu hóa khả năng bảo vệ, phục hồi | Quyền quản trị công cụ có đồng thời cho phép đọc mọi bí mật hoặc xóa mọi bằng chứng không? |
| Nhà cung cấp, đơn vị hỗ trợ | Quyền mở lâu sau khi hết nhu cầu; thiếu liên kết với cá nhân | Ai bảo trợ quyền truy cập, khi nào hết hạn và bằng chứng phiên nằm ở đâu? |
| Tài khoản khẩn cấp | Quyền mạnh; ít được sử dụng; có thể bỏ qua luồng thông thường | Khi nào được dùng, ai được cảnh báo và việc kiểm tra sau sử dụng diễn ra thế nào? |

Mức ưu tiên không nên chỉ dựa vào nhãn loại tài khoản. Một tài khoản dịch vụ nhỏ nhưng đọc được bí mật quản trị có thể cần được xử lý trước một tài khoản quản trị cô lập trong môi trường thử nghiệm.

## 5. Chuỗi ví dụ: từ credential bị lộ đến sự cố production

Xét một hệ thống giả định:

- Một tài khoản dịch vụ được pipeline dùng để triển khai ứng dụng.
- Credential của tài khoản có hiệu lực dài hạn và xuất hiện trong đầu ra của một tác vụ.
- Vai trò triển khai có thể sửa cả tài nguyên ứng dụng lẫn một số chính sách truy cập không cần thiết cho việc triển khai.
- Nhiều pipeline cùng dùng tài khoản này và log chưa gắn rõ từng lần chạy.

Chuỗi rủi ro có thể diễn ra như sau:

```text
Credential bị lộ từ tác vụ
        |
        v
Có thể xác thực dưới danh tính triển khai
        |
        v
Sử dụng các quyền hiện có trên production
        |
        +--> Thay đổi cấu hình hoặc đưa mã không mong muốn vào ứng dụng
        |
        +--> Mở rộng quyền nếu chính sách hiện tại cho phép
        |
        +--> Truy cập tài nguyên khác nằm trong phạm vi vai trò
```

Các nhánh này là khả năng theo giả định của ví dụ, không phải mọi tài khoản triển khai đều có thể làm được. Khi điều tra thực tế phải đối chiếu quyền, điều kiện truy cập, chính sách tài nguyên và log đã phát sinh.

Vì sao đây là vấn đề PAM?

1. **Credential tồn tại lâu:** người có credential có thể có cơ hội dùng nó trong một khoảng thời gian dài.
2. **Quyền dư:** vai trò triển khai được phép thực hiện thao tác quản trị danh tính ngoài nhu cầu công việc.
3. **Dùng chung danh tính:** khó xác định pipeline và lần chạy tạo ra từng hành động.
4. **Phạm vi rộng:** một credential có thể tác động nhiều ứng dụng hoặc môi trường.
5. **Thu hồi chưa rõ:** chỉ sửa lỗi in log không làm credential đã lộ mất hiệu lực.

Hướng giảm rủi ro gồm: giới hạn vai trò triển khai theo tài nguyên và thao tác; dùng danh tính riêng theo workload hoặc môi trường khi phù hợp; cấp credential ngắn hạn dựa trên quan hệ tin cậy được giới hạn; bảo vệ việc sửa pipeline; thu hồi credential đã lộ; và liên kết hành động với lần chạy cụ thể.

Với một sự cố đang diễn ra, cũng cần kiểm tra các thay đổi quyền, credential mới và phiên còn hiệu lực. Phục hồi phải bao gồm tác động đã phát sinh, không chỉ thay phương tiện đăng nhập ban đầu.

## 6. PAM giảm rủi ro bằng những cơ chế nào?

Các cơ chế cần được lựa chọn theo đường rủi ro thực tế. Mua một công cụ hoặc bật một tính năng riêng lẻ không làm mọi tài khoản đặc quyền trở nên an toàn.

| Cơ chế | Rủi ro được giảm | Điều kiện và giới hạn cần hiểu |
| --- | --- | --- |
| Kiểm kê danh tính và quyền | Bỏ sót tài khoản, quyền dư, tài khoản không có chủ sở hữu | Cần kiểm kê cả quyền trực tiếp, quyền kế thừa và đường nhận quyền gián tiếp |
| Least privilege — đặc quyền tối thiểu | Phạm vi tác động quá rộng | Phải gắn quyền với nhiệm vụ và tài nguyên; vai trò có tên hẹp vẫn có thể chứa quyền mạnh |
| JIT — Just-in-Time | Quyền mạnh tồn tại lâu ngoài thời gian cần thiết | Cần kiểm soát điều kiện cấp, thời hạn, thu hồi và phiên hoặc credential liên quan |
| JEA — Just Enough Administration | Người thực hiện được nhiều thao tác hơn nhiệm vụ yêu cầu | Cần giới hạn tập hành động thực sự; một thao tác được phép nhưng gọi được công cụ tùy ý có thể phá vỡ giới hạn |
| Vault và phân phối bí mật có kiểm soát | Credential bị chia sẻ, lưu rải rác, không rõ ai lấy | Vault cũng là tài sản nhạy cảm; credential đã được lấy ra vẫn cần kiểm soát cách sử dụng |
| Luân chuyển và thu hồi credential | Credential bị lộ vẫn tiếp tục dùng được | Phải xác định loại credential, ứng dụng phụ thuộc và cơ chế vô hiệu hóa; tránh gây gián đoạn do bỏ sót nơi sử dụng |
| Xác thực mạnh, kiểm tra ngữ cảnh | Người không phù hợp có thể nhận hoặc sử dụng quyền | MFA phù hợp với nhiều luồng con người nhưng không thay thế kiểm soát workload, token và phiên |
| Kiểm soát, giám sát phiên | Thiếu quan sát khi thực hiện thao tác đặc quyền | Phiên API và tác vụ tự động cần audit phù hợp; không phải mọi thao tác đều đi qua một phiên tương tác có thể ghi hình |
| Tách nhiệm vụ và bảo vệ bằng chứng | Một người vừa thực hiện thay đổi vừa xóa dấu vết hoặc tự phê duyệt | Cần áp dụng theo mức rủi ro; quyền khẩn cấp phải có cách kiểm soát và xem xét riêng |

### Phân biệt JIT và JEA bằng một nhiệm vụ

Nhiệm vụ: khởi động lại một dịch vụ production trong thời gian xử lý sự cố.

- **JIT** trả lời: “Trong khoảng thời gian nào người này được nhận quyền?”
- **JEA** trả lời: “Trong khoảng thời gian đó, người này được thực hiện chính xác những hành động nào?”

Cấp quyền quản trị toàn máy trong 15 phút có giới hạn thời gian nhưng vẫn rất rộng về chức năng. Cho phép duy nhất thao tác khởi động lại dịch vụ, trong phạm vi cần thiết và với thời hạn phù hợp, giảm cả hai chiều rủi ro.

Cần kiểm tra khi hết hạn điều gì thực sự bị thu hồi. Một phiên đã mở, credential đã phát hành hoặc token đã nhận có thể có vòng đời khác với bản ghi cấp vai trò. Thiết kế phải chỉ rõ cách xử lý các trường hợp đó.

## 7. Vì sao vault, MFA và ghi phiên vẫn chưa đủ?

### Có vault nhưng quyền vẫn quá rộng

Vault giúp bảo vệ và kiểm soát việc lấy bí mật. Nếu bí mật đó mở toàn bộ production và ai cũng có thể lấy, phạm vi hậu quả vẫn lớn. Nếu một credential cũ đã được sao chép ra ngoài mà vẫn còn hiệu lực, việc đưa bản hiện tại vào vault không tự thu hồi bản cũ.

### Có MFA nhưng phiên có thể bị lạm dụng

MFA làm mạnh bước xác thực của con người, nhưng hiệu quả phụ thuộc loại yếu tố và luồng sử dụng. Một phiên hoặc token còn hiệu lực có thể tiếp tục mang quyền theo cơ chế của hệ thống. Vì vậy cần kết hợp kiểm soát phiên, thiết bị, điều kiện truy cập và thu hồi phù hợp.

Với dịch vụ tự động, không nên thiết kế bằng cách buộc người vận hành chia sẻ mã MFA. Hướng phù hợp thường là danh tính workload, quan hệ tin cậy có giới hạn và credential có vòng đời được quản lý.

### Có ghi hình nhưng vẫn không quy trách nhiệm được

Một bản ghi mang tên tài khoản dùng chung, thiếu người yêu cầu hoặc thiếu mã phiên liên kết sẽ khó phục vụ điều tra. Việc ghi hình cũng có thể bỏ sót thao tác API hoặc đường truy cập ngoài hệ thống quản lý phiên.

Bản ghi cần được bảo vệ vì có thể chứa dữ liệu nhạy cảm. Không chủ động đưa mật khẩu, token hay bí mật đầy đủ vào log để làm “bằng chứng”; cần áp dụng che giấu và giới hạn truy cập thích hợp.

### Có phê duyệt nhưng người duyệt thiếu thông tin

Phê duyệt chung chung “cho quyền admin để xử lý sự cố” khó giúp người duyệt đánh giá phạm vi cần thiết. Yêu cầu nên nêu tài nguyên, nhiệm vụ, khoảng thời gian, người thực hiện và ngữ cảnh công việc.

Phê duyệt là một phần của kiểm soát, không thay thế giới hạn quyền trong hệ thống.

## 8. Bằng chứng nào giúp kiểm toán và ứng phó sự cố?

Đối với một lượt sử dụng quyền đặc biệt, nên có khả năng liên kết các thông tin sau theo mức phù hợp với hệ thống:

| Nhóm bằng chứng | Thông tin cần làm rõ |
| --- | --- |
| Danh tính và quyền | Người hoặc workload nào yêu cầu; sử dụng danh tính kỹ thuật nào; được cấp quyền gì |
| Mục đích và quyết định | Nhiệm vụ hoặc sự cố liên quan; ai hoặc chính sách nào phê duyệt; điều kiện đã được kiểm tra |
| Phạm vi và thời gian | Môi trường, tài nguyên, thời điểm bắt đầu, hết hạn và thời điểm thu hồi thực tế |
| Hoạt động | Phiên hoặc lần chạy nào đã thực hiện thao tác; hành động nhạy cảm nào thành công hoặc thất bại |
| Vòng đời credential | Credential nào được phát hành, lấy hoặc thu hồi, qua định danh an toàn thay vì giá trị bí mật |
| Toàn vẹn và bảo vệ | Nguồn log, thời gian đủ để đối chiếu, quyền truy cập bằng chứng và các thay đổi cấu hình ghi log |

Ví dụ về **bản ghi minh họa**, không phải cấu hình cho một sản phẩm cụ thể:

```text
request_id: PAM-EXAMPLE-1042
actor: engineer-a
target_identity: production-service-operator
target_resource: production/application-a
allowed_action: restart_application_service
reason: incident-example-27
approved_by: operations-duty-lead
valid_from: 2026-11-26T02:00:00Z
valid_until: 2026-11-26T02:20:00Z
session_id: session-example-81
revocation_result: confirmed
```

Bản ghi yêu cầu quyền chưa chứng minh thao tác thực tế đã xảy ra. Cần đối chiếu với log ở hệ thống đích hoặc nguồn audit phù hợp. Ngược lại, một log thao tác không tự chứng minh yêu cầu đã được phê duyệt đúng quy trình.

Thời hạn lưu, mức chi tiết và quyền xem bằng chứng cần được xác định theo nhu cầu điều tra, chính sách tổ chức và yêu cầu áp dụng. Bài này không đặt một thời hạn cố định cho mọi hệ thống.

## 9. Ưu tiên xử lý rủi ro như thế nào?

Một điểm bắt đầu hữu ích là tìm các danh tính có nhiều yếu tố sau cùng lúc:

- Có thể cấp quyền, đọc bí mật dùng chung hoặc điều khiển hạ tầng trọng yếu.
- Có quyền thường trực và credential dài hạn.
- Dùng chung cho nhiều người, workload hoặc môi trường.
- Có đường truy cập ngoài kiểm soát hoặc thiếu chủ sở hữu rõ ràng.
- Có thể tác động bản sao lưu, công cụ bảo mật hoặc bằng chứng.
- Chưa có cách thu hồi đã được xác nhận.

Trình tự xử lý có thể gồm:

1. **Xác định chủ sở hữu và mục đích.** Không thể đánh giá quyền cần thiết nếu không biết danh tính phục vụ ai và công việc gì.
2. **Vẽ phạm vi tác động.** Liệt kê tài nguyên nhạy cảm, quyền cấp tiếp và quan hệ tin cậy liên quan.
3. **Đóng các đường lộ hoặc sử dụng quyền không được quản lý.** Bao gồm bản sao credential, đường đăng nhập trực tiếp và quyền không còn nhu cầu.
4. **Thu hẹp quyền và thời gian.** Áp dụng least privilege, JIT/JEA theo tính chất công việc.
5. **Kiểm soát vòng đời và bằng chứng.** Xác nhận cách cấp, sử dụng, theo dõi, thu hồi và phục hồi sau sự cố.

Đối với dịch vụ đang chạy, thay đổi quyền hoặc credential cần có kế hoạch kiểm tra phụ thuộc và khôi phục phù hợp. Thu hẹp quyền thiếu hiểu biết có thể gây gián đoạn; điều đó là lý do phải hiểu luồng sử dụng, không phải lý do giữ quyền dư vô thời hạn.

### Một ví dụ đo mức phơi lộ theo thời gian

Giả sử 10 người đều giữ cùng một quyền quản trị trong 24 giờ:

- Tổng thời gian quyền sẵn có: 10 × 24 = **240 giờ-danh tính**.

Nếu cùng 10 người chỉ nhận quyền trong 1 giờ phù hợp với nhiệm vụ:

- Tổng thời gian quyền sẵn có: 10 × 1 = **10 giờ-danh tính**.

Ví dụ này chỉ minh họa việc giảm thời gian tồn tại của quyền. Không thể kết luận rằng xác suất sự cố giảm cùng tỷ lệ: phạm vi quyền, thời điểm sử dụng, mức nhạy cảm và chất lượng kiểm soát cũng quyết định rủi ro.

## 10. Tình huống tự đánh giá

Một nhóm vận hành có các điều kiện sau:

- Sáu người dùng chung một tài khoản quản trị production.
- Mật khẩu được lưu trong vault và thay mỗi tháng.
- Sau khi lấy mật khẩu, người dùng có thể đăng nhập trực tiếp vào máy chủ.
- Tài khoản có thể thay cấu hình ứng dụng, quản lý người dùng và sửa log cục bộ.
- Không có thời hạn quyền theo nhiệm vụ; log truy cập vault chưa được liên kết với phiên ở máy đích.

Hãy phân tích theo bốn câu hỏi:

1. **Quyền mạnh ở đâu?** Quyền quản lý người dùng và sửa log vượt ra ngoài nhiều nhiệm vụ vận hành ứng dụng thông thường.
2. **Ai có thể dùng quyền?** Cả sáu người và bất kỳ ai có được bản sao credential còn hiệu lực; log lấy mật khẩu chưa đủ xác định người thực hiện từng thao tác.
3. **Quyền tồn tại bao lâu?** Quyền quản trị thường trực; chu kỳ đổi mật khẩu không biến quyền thành quyền theo nhiệm vụ.
4. **Có thể điều tra và thu hồi không?** Đường đăng nhập trực tiếp, tài khoản dùng chung và khả năng sửa log làm việc quy trách nhiệm khó hơn. Cần kiểm tra thêm cách xử lý phiên còn hiệu lực khi đổi mật khẩu.

Một hướng cải thiện hợp lý là dùng danh tính cá nhân ở bước yêu cầu, giới hạn hành động theo nhiệm vụ, cấp quyền có thời hạn khi phù hợp, kiểm soát các đường truy cập trực tiếp và liên kết bằng chứng giữa yêu cầu, phiên và log hệ thống đích. Quyền khẩn cấp cần có chủ sở hữu, điều kiện sử dụng, cảnh báo và xem xét sau sử dụng.

Không thể kết luận chỉ từ việc “đã có vault” rằng toàn bộ chuỗi đặc quyền đã được kiểm soát.

## 11. Những điểm cần ghi nhớ

- Tài khoản đặc quyền rủi ro cao vì quyền có thể tạo tác động lớn, lan sang hệ thống khác hoặc làm suy yếu chính cơ chế bảo vệ và phục hồi.
- Danh tính có đặc quyền bao gồm con người, tài khoản dịch vụ, workload, pipeline và các tài khoản quản trị công cụ bảo mật; cần đánh giá cả quyền gián tiếp.
- Quản lý credential chỉ là một phần của PAM. Phạm vi quyền, thời hạn, đường sử dụng và khả năng quy trách nhiệm đều phải được kiểm soát.
- Least privilege giảm phạm vi; JIT giảm thời gian; JEA giới hạn hành động; vault và luân chuyển quản lý bí mật; giám sát và bằng chứng hỗ trợ phát hiện, kiểm toán và ứng phó.
- Một thiết kế PAM cần giải thích được: **ai hoặc workload nào được làm gì, trên tài nguyên nào, khi nào, vì lý do gì, và quyền đã được thu hồi ra sao**.