# Permission theo thời gian

## 1. Mục tiêu và bối cảnh

Trong chương **Least privilege**, giới hạn quyền theo thời gian bổ sung một câu hỏi quan trọng cho việc phân quyền: ngoài việc được làm gì và trên tài nguyên nào, chủ thể **được làm vào thời điểm nào và đến khi nào**?

Với PAM, đặc quyền của tài khoản quản trị, tài khoản dịch vụ và workload cần gắn với nhu cầu thực tế. Một quyền phù hợp với nhiệm vụ hôm nay có thể không còn cần vào ngày mai. Một thao tác được phép trong cửa sổ bảo trì cũng chưa chắc được phép ngoài cửa sổ đó.

Sau bài học, bạn có thể:

- Phân biệt lịch được phép truy cập, thời hạn cấp quyền, thời hạn credential và thời hạn phiên.
- Mô tả cửa sổ hiệu lực bằng thời điểm bắt đầu và kết thúc rõ ràng.
- Áp dụng giới hạn thời gian cho quyền một lần, quyền kích hoạt theo nhu cầu và quyền theo lịch lặp.
- Nhận diện khoảng trống do token, phiên, cache và cơ chế thu hồi chậm.
- Thiết kế bằng chứng để xác nhận quyền đã được sử dụng và kết thúc đúng điều kiện.

## 2. Quyền theo thời gian là gì?

**Permission theo thời gian** là quyền có điều kiện hiệu lực phụ thuộc vào thời gian. Thời gian có thể giới hạn ngày bắt đầu, hạn kết thúc, khoảng hoạt động trong ngày, thời lượng mỗi lần kích hoạt hoặc sự kết hợp của các yếu tố đó.

Một quyền nên được mô tả theo bộ thông tin:

> **Chủ thể → hành động → tài nguyên → điều kiện thời gian → điều kiện khác → điểm thực thi.**

Ví dụ: kỹ sư trực ca được khởi động lại dịch vụ A ở sản xuất trong một lần kích hoạt tối đa 30 phút, chỉ nằm trong cửa sổ bảo trì đã duyệt, thông qua cơ chế vận hành được chỉ định.

Điều kiện thời gian không thay thế phạm vi quyền. Cấp quyền quản trị mọi hệ thống trong vài phút vẫn có thể tạo tác động lớn. Least privilege cần giới hạn đồng thời hành động, tài nguyên và thời gian phù hợp với nhiệm vụ.

### 2.1. Các dạng giới hạn thường gặp

| Dạng | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| Khoảng ngày hiệu lực | Quyền chỉ hợp lệ giữa hai mốc | Hỗ trợ kỹ thuật trong giai đoạn hợp đồng được giao |
| Cửa sổ một lần | Chỉ cho phép trong một khoảng đã định | Bảo trì từ 22:00 đến 23:00 của một ngày cụ thể |
| Thời lượng từ khi kích hoạt | Quyền kéo dài tối đa một khoảng kể từ lúc bắt đầu | Tối đa 30 phút sau khi kích hoạt thành công |
| Lịch lặp | Mỗi lần đến lịch có một khoảng được phép | Một tác vụ được phép chạy trong cửa sổ hằng tuần |
| Kết thúc theo sự kiện, có hạn tối đa | Quyền kết thúc khi công việc xong hoặc đến hạn, tùy điều kiện nào xảy ra trước | Kết thúc cùng lần chạy triển khai, nhưng không vượt giới hạn tuyệt đối |

Các giá trị thời gian trong bài chỉ phục vụ giải thích. Thời hạn thực tế cần dựa trên nhiệm vụ, mức tác động, khả năng thực thi và yêu cầu vận hành.

### 2.2. Lịch làm việc không tự tạo ra nhu cầu đặc quyền

Một người làm ca đêm không nhất thiết cần quyền quản trị suốt ca. Lịch có thể là một điều kiện để được yêu cầu quyền, còn việc kích hoạt phải gắn với nhiệm vụ cụ thể.

Tương tự, một lịch bảo trì có thể cho phép thực hiện thay đổi, nhưng không có nghĩa mọi thành viên của nhóm đều cần toàn quyền trong toàn bộ lịch. Cần xác định ai, thao tác nào và tài nguyên nào được phép.

## 3. Phân biệt những loại thời hạn dễ bị nhầm

| Đối tượng | Thời hạn có ý nghĩa gì? | Điều chưa thể kết luận chỉ từ thời hạn đó |
| --- | --- | --- |
| Phê duyệt | Quyết định còn được dùng để kích hoạt hoặc thực hiện trong phạm vi nào | Quyền đã được cấp thành công hay chưa |
| Tư cách đủ điều kiện | Chủ thể còn được yêu cầu hoặc kích hoạt quyền không | Chủ thể hiện đang có quyền hay không |
| Quyền hiệu lực | Một bản cấp quyền còn cho phép hành động không | Có quyền tương đương từ nguồn khác hay không |
| Credential | Phương tiện xác thực còn được chấp nhận không | Tài khoản hoặc mọi phiên đã chấm dứt hay chưa |
| Tài khoản | Danh tính có được phép sử dụng theo trạng thái và cơ chế tài khoản không | Token hoặc kết nối cũ đã bị thu hồi hay chưa |
| Phiên | Một phiên cụ thể còn hoạt động không | Có thể mở phiên mới qua đường khác hay không |
| Lịch tác vụ | Tác vụ được dự kiến bắt đầu lúc nào | Hệ thống đích sẽ từ chối hành động ngoài lịch hay không |

Mật khẩu hết hạn không nhất thiết là tài khoản hết hạn. Trong một số hệ thống, nó có thể dẫn đến yêu cầu đổi mật khẩu. Token hết hạn cũng không mặc nhiên hủy mọi công việc đã được khởi chạy bằng token đó.

Vì vậy, tài liệu phân quyền cần nói rõ thời hạn đang áp dụng cho lớp nào và thành phần nào chịu trách nhiệm thực thi.

## 4. Mô tả cửa sổ hiệu lực chính xác

### 4.1. Chọn quy ước biên rõ ràng

Một quy ước dễ kiểm tra là dùng khoảng thời gian có đầu được tính và cuối không được tính:

```text
Cho phép theo thời gian khi:
    not_before <= thời_gian_tin_cậy < expires_at
```

Với cửa sổ 22:00–23:00, quyền bắt đầu có thể hợp lệ lúc 22:00 và không còn hợp lệ từ đúng 23:00. Đây là quy ước thiết kế minh họa; khi dùng nền tảng cụ thể phải đối chiếu cách nó biểu diễn và thực thi mốc thời gian.

Cần kiểm tra `expires_at` lớn hơn `not_before`. Một khoảng rỗng, mốc bị đảo hoặc dữ liệu không xác định múi giờ phải được xử lý rõ, tránh tự suy đoán rồi cấp quyền ngoài mong muốn.

### 4.2. Không để kích hoạt muộn làm vượt giới hạn tuyệt đối

Nếu có thời lượng tối đa và cửa sổ đã duyệt, thời điểm kết thúc phải chịu cả hai ràng buộc. Một mô hình minh họa là:

```text
kết_thúc_hiệu_lực = thời_điểm_sớm_nhất_trong(
    thời_điểm_kích_hoạt + thời_lượng_được_duyệt,
    kết_thúc_cửa_sổ_được_duyệt,
    hạn_kết_thúc_theo_chính_sách
)
```

Ví dụ, cửa sổ kết thúc lúc 23:00, thời lượng tối đa là 30 phút:

- Kích hoạt lúc 22:12 thì kết thúc lúc 22:42.
- Kích hoạt lúc 22:50 thì chỉ còn đến 23:00.
- Đến 23:00 mà chưa kích hoạt thì không thể dùng phê duyệt đó để bắt đầu một lần truy cập mới.

Nếu cần thêm thời gian, phải có quyết định gia hạn phù hợp. Không nên âm thầm tính một cửa sổ mới từ thời điểm bắt đầu muộn.

### 4.3. Tách hạn kích hoạt và hạn sử dụng

Phê duyệt có thể quy định phải bắt đầu trước một mốc, đồng thời quyền sau khi bắt đầu còn chịu một hạn kết thúc khác. Hai mốc này cần được đặt tên và lưu riêng nếu chúng có ý nghĩa khác nhau.

Ví dụ, được kích hoạt chậm nhất lúc 22:30 nhưng mọi hoạt động phải kết thúc trước 23:00. Một lần kích hoạt sau 22:30 không hợp lệ dù cửa sổ chung chưa đóng.

Không nên giữ một quyết định phê duyệt vô thời hạn để dùng lại cho một nhiệm vụ đã thay đổi bối cảnh.

## 5. Múi giờ, lịch lặp và nguồn thời gian

### 5.1. Lưu mốc rõ ràng, hiển thị theo ngữ cảnh

Một mốc như “22:00 ngày 10” thiếu tháng, năm và múi giờ sẽ gây hiểu nhầm giữa các nhóm. Mốc tuyệt đối cần có ngày đầy đủ và múi giờ hoặc độ lệch tương ứng.

Ví dụ minh họa cùng một thời điểm:

```text
2026-12-10T22:00:00+07:00
2026-12-10T15:00:00Z
```

Hệ thống có thể chuẩn hóa mốc tuyệt đối để xử lý và hiển thị theo múi giờ của công việc. Báo cáo cần đủ thông tin để người đọc đối chiếu, không chỉ hiện một giờ địa phương thiếu ngữ cảnh.

### 5.2. Lịch lặp khác với mốc tuyệt đối

“22:00 theo giờ địa phương mỗi thứ Sáu” là một quy tắc lịch, không phải một mốc cố định. Khi lịch áp dụng cho vùng có thay đổi giờ theo mùa, một giờ địa phương có thể bị lặp hoặc không xuất hiện trong ngày chuyển đổi.

Thiết kế lịch cần xác định múi giờ, cách xử lý trường hợp đó và cách chuyển mỗi lần xuất hiện thành cửa sổ hiệu lực cụ thể. Dùng một độ lệch cố định không phải lúc nào cũng tương đương với ý định “giờ địa phương” của một vùng.

Cửa sổ đi qua nửa đêm cũng phải rõ: “thứ Sáu 23:00 đến thứ Bảy 01:00” tránh nhập nhầm thành một khoảng kết thúc trước khi bắt đầu. Nếu có quy tắc ngày nghỉ hoặc ngoại lệ, chúng cần được biểu diễn trong chính sách thay vì suy ra từ lịch làm việc chung.

### 5.3. Dùng nguồn thời gian đáng tin cậy

Không nên cho phép người yêu cầu quyết định quyền còn hạn chỉ bằng đồng hồ trên máy của họ. Thành phần thực thi cần nguồn thời gian và cơ chế đồng bộ phù hợp với kiến trúc.

Khi có nhiều thành phần, phải hiểu độ lệch đồng hồ và độ trễ xử lý. Không tự thêm một khoảng ân hạn ở từng lớp khiến thời gian thực tế rộng hơn điều đã được duyệt.

Nếu độ không chắc chắn của thời gian không đáp ứng yêu cầu, cần có chính sách rõ cho việc cấp mới và kết thúc. Lỗi đồng hồ không nên mặc nhiên biến thành quyền thường trực.

## 6. Đặt kiểm tra thời gian ở đâu?

### 6.1. Giao diện chỉ là nơi biểu diễn

Một nút bị ẩn sau 23:00 không chặn được API hoặc một phiên đã mở. Kiểm tra cần nằm ở điểm có khả năng quyết định hoặc thực thi truy cập: hệ thống phân quyền tại đích, broker, bộ thực thi chức năng hay thành phần phù hợp khác.

Phải xác định phạm vi bảo vệ. Nếu broker chỉ kiểm soát đường qua broker, vẫn cần xử lý các đường trực tiếp có quyền tương đương.

### 6.2. Tác vụ lịch không thay thế kiểm tra truy cập

Một tác vụ tự động thêm thành viên nhóm lúc đầu cửa sổ và gỡ lúc cuối cửa sổ có thể hỗ trợ quản lý. Nhưng nó còn phụ thuộc vào việc tác vụ chạy, kết nối tới đích, độ trễ đồng bộ và trạng thái phiên.

Nếu tác vụ gỡ quyền lỗi, thành viên có thể còn tồn tại ngoài dự kiến. Cần có đối chiếu trạng thái, cảnh báo và người xử lý; không thể chỉ nhìn lịch đã cấu hình rồi coi thời hạn được bảo đảm.

### 6.3. Mỗi lần sử dụng cần được xét theo cơ chế thực tế

Một số nền tảng kiểm tra quyền khi cấp token hoặc mở phiên; nền tảng khác có thể kiểm tra tại từng yêu cầu. Cách giới hạn thời gian phải phù hợp với mô hình đó.

Nếu kiểm tra quyền chỉ ở đầu phiên, cần quyết định phiên sẽ bị giới hạn hoặc kết thúc thế nào. Nếu dùng quyền trong token, cần kiểm tra thời hạn, phạm vi và cơ chế thu hồi được nền tảng hỗ trợ.

Chỉ biết thời hạn vai trò không đủ suy ra thời điểm mọi hành động tại đích sẽ bị từ chối.

## 7. Token, credential, cache và phiên

### 7.1. Không cấp phương tiện sống vượt ràng buộc đã duyệt

Nếu một quyền kết thúc lúc 23:00 mà token được cấp lúc 22:55 vẫn cho phép truy cập đến 23:55, giới hạn thời gian có thể bị kéo dài tại lớp sử dụng token, trừ khi còn cơ chế khác kiểm tra và chặn đúng hạn.

Cần thiết kế quan hệ giữa thời hạn quyền và thời hạn phương tiện xác thực. Một hướng là chặn thời hạn phương tiện trong giới hạn được phép, kết hợp kiểm tra lại hoặc thu hồi theo khả năng của đích.

Nếu có ủy quyền tiếp, thời gian quyền con cũng cần chịu các giới hạn của quyền nguồn theo chính sách. Một quyền ngắn hạn không nên trở thành cơ sở tự tạo quyền lâu dài ngoài phạm vi đã được cho phép.

### 7.2. Cache quyết định phải giữ được điều kiện hết hạn

Một kết quả “allow” được cache trong 15 phút có thể không còn đúng nếu quyền chỉ còn hai phút. Việc dùng lại cache cần xét hạn quyền và những thay đổi có thể làm quyết định mất hiệu lực.

Không nên chỉ dựa vào TTL chung. Thành phần dùng cache cần giữ và kiểm tra điều kiện hết hạn thích hợp, cũng như xử lý sự kiện hủy hoặc thay đổi quyền theo thiết kế.

Nếu không thể đồng bộ thu hồi tức thì, giới hạn độ trễ cần được biết và phù hợp với yêu cầu. Một lời hứa thu hồi ngay không thể dựa vào cache còn chấp nhận quyết định cũ trong thời gian dài.

### 7.3. Luân chuyển credential không phải thu hồi permission

Đổi mật khẩu hoặc bí mật xử lý phương tiện xác thực. Nó không tự xóa vai trò đã gán cho tài khoản và có thể không kết thúc phiên đã xác thực.

Ngược lại, gỡ permission không bảo đảm credential đã lộ không còn hữu dụng trên tài nguyên khác. PAM cần quản lý cả quyền, credential và phiên trong cùng ngữ cảnh nhiệm vụ.

### 7.4. Idle timeout khác absolute timeout

**Idle timeout** kết thúc phiên sau một khoảng không hoạt động. **Absolute timeout** đặt giới hạn tổng thời gian phiên dù người dùng vẫn hoạt động.

Một phiên liên tục phát sinh hoạt động có thể không bao giờ chạm idle timeout. Vì vậy, dùng idle timeout riêng lẻ chưa đáp ứng một cửa sổ đặc quyền phải kết thúc ở mốc cố định.

## 8. Hết hạn, hủy sớm và gia hạn

### 8.1. Phân biệt hết hạn theo chính sách với thu hồi đã xác nhận

Đến hạn nghĩa là quyền không còn được phép sử dụng theo chính sách. Thu hồi đã xác nhận nghĩa là cơ chế kỹ thuật tương ứng đã thực hiện đúng kết quả cần đạt.

Hai thời điểm có thể khác nhau nếu nền tảng truyền thay đổi chậm, phiên còn tồn tại hoặc thao tác thu hồi lỗi. Cần theo dõi khoảng chênh lệch này và không đóng bản ghi như thể đã hoàn tất khi trạng thái tại đích chưa rõ.

### 8.2. Hủy trước hạn

Nhiệm vụ hoàn thành sớm, người dùng đổi vai trò hoặc có dấu hiệu xâm nhập đều có thể đòi hỏi kết thúc trước thời hạn. Thiết kế chỉ hỗ trợ đợi token tự hết hạn có giới hạn khác với thiết kế hỗ trợ thu hồi chủ động.

Phải mô tả được giới hạn đó và chọn thời lượng, cơ chế phiên cùng biện pháp xử lý phù hợp. Trong sự cố, cần kiểm tra những thay đổi hoặc phương tiện khác đã được tạo để tiếp tục truy cập.

### 8.3. Gia hạn có kiểm soát

Gia hạn cần kiểm tra lại nhu cầu, phạm vi, thời điểm mới và các điều kiện còn hợp lệ. Lưu người hoặc chính sách ra quyết định cùng lý do và mốc trước, sau.

Không nên cho phép một phiên tự kéo dài chỉ vì người dùng còn thao tác. Với workload, việc tác vụ còn chạy cũng chưa đủ nếu nó đã vượt giới hạn hoặc thay đổi phạm vi được duyệt.

Có thể cho phép gia hạn tự động trong một chính sách rõ ràng, nhưng phải có điều kiện và giới hạn. Nếu được gia hạn liên tục không có trần hay đánh giá, quyền thực tế có thể trở thành thường trực.

## 9. Nhiều nguồn quyền và lịch chồng lấn

Một tài khoản có thể nhận cùng khả năng từ quyền trực tiếp, nhóm, vai trò JIT và chính sách tài nguyên. Hết hạn một bản cấp chưa chắc khiến hành động bị từ chối nếu một nguồn khác vẫn cho phép.

Trong một mô hình minh họa, hành động có thể còn được phép khi tồn tại một bản cấp hợp lệ phù hợp. Tuy nhiên, quy tắc kết hợp và ưu tiên từ chối khác nhau giữa nền tảng; không được áp dụng máy móc mô hình này cho mọi hệ thống.

Điểm cần kiểm tra là **quyền hiệu lực từ toàn bộ nguồn**, không chỉ trạng thái của một yêu cầu.

Ví dụ:

| Nguồn | Thời gian | Phạm vi |
| --- | --- | --- |
| Bản cấp A | 22:00–22:30 | Khởi động lại dịch vụ A |
| Bản cấp B | 22:20–22:45 | Khởi động lại dịch vụ A |
| Nhóm quản trị thường trực | Không gắn cửa sổ nhiệm vụ | Quyền rộng hơn trên máy chủ |

Kết thúc bản cấp A lúc 22:30 không bảo đảm mất khả năng khởi động lại. Bản cấp B có thể còn hợp lệ, còn nhóm thường trực có thể làm mất ý nghĩa của cả hai giới hạn.

Với tài khoản dùng chung, một người hết hạn nhưng người khác còn được phép cũng tạo vấn đề ràng buộc truy cập. Giữ quyền ở tài khoản không cho biết ai còn được dùng phiên hoặc credential. Cần danh tính, phiên hoặc cơ chế cấp được liên kết riêng theo người và nhiệm vụ.

## 10. Tác vụ dài và hiệu lực của hành động đã bắt đầu

Một câu hỏi quan trọng là quyền phải còn hiệu lực lúc bắt đầu, trong suốt thao tác hay tại các điểm kiểm tra cụ thể.

Ví dụ, một yêu cầu xuất dữ liệu được chấp nhận trước hạn nhưng tiếp tục truyền dữ liệu sau hạn. Một tác vụ triển khai có thể đã tạo thay đổi trước khi quyền kết thúc. Từ chối yêu cầu mới không tự đảo ngược các thay đổi đã xảy ra.

Thiết kế cần xác định:

- Những thao tác nào chỉ cần được chấp nhận trong cửa sổ và những thao tác nào phải bị giới hạn suốt thời gian chạy.
- Cách dừng hoặc hoàn tất an toàn khi đến hạn.
- Ai có quyền quyết định tiếp tục, gia hạn hoặc hoàn tác.
- Bằng chứng về thời điểm chấp nhận, bắt đầu, kết thúc và kết quả.

Không nên mặc định cắt mọi kết nối là luôn đúng trong mọi tình huống. Việc dừng giữa chừng có thể ảnh hưởng dữ liệu hoặc tính sẵn có. Nếu nhiệm vụ cần thêm cơ chế hoàn tất an toàn, cơ chế đó phải được thiết kế và ghi rõ phạm vi, thay vì để phiên tiếp tục vô hạn ngoài chính sách.

## 11. Ví dụ xuyên suốt: bảo trì dịch vụ A

### 11.1. Yêu cầu và giới hạn

Một kỹ sư được phép khởi động lại dịch vụ A trong cửa sổ 22:00–23:00 của một ngày cụ thể, theo múi giờ đã được xác định. Mỗi lần kích hoạt tối đa 30 phút, phải bắt đầu trước 22:40. Quyền không bao gồm sửa chính sách bảo mật, đọc bí mật của dịch vụ khác hoặc tạo tài khoản mới.

Kỹ sư kích hoạt lúc 22:12. Thời điểm kết thúc tính theo giới hạn là 22:42. Nếu cần tiếp tục sau đó, phải có gia hạn hợp lệ; việc cửa sổ chung còn đến 23:00 không tự kéo dài lần kích hoạt.

### 11.2. Đặc tả minh họa

Mã giả sau dùng để mô tả chính sách, không phải cấu hình triển khai:

```text
Phạm vi:
  chủ_thể = kỹ_sư_được_giao
  hành_động = khởi_động_lại_dịch_vụ
  tài_nguyên = dịch_vụ_A
  môi_trường = sản_xuất

Điều kiện kích hoạt:
  yêu_cầu đã_được_duyệt và chưa_bị_hủy
  thời_gian_tin_cậy thuộc cửa_sổ được_duyệt
  thời_gian_tin_cậy trước hạn_chót_kích_hoạt
  danh_tính và phạm_vi vẫn khớp nội_dung được_duyệt

Khi kích hoạt:
  ghi thời_điểm quyền thực_sự có_hiệu_lực
  tính kết_thúc theo tất_cả giới_hạn liên_quan
  cấp phương_tiện_truy_cập phù_hợp với giới_hạn đó
  ghi mã_lần_cấp để liên_kết phiên và hành_động

Khi sử dụng:
  thực_thi kiểm_tra thời_gian tại lớp được_chỉ_định
  ràng_buộc hành_động và tài_nguyên với lần_cấp
  ghi kết_quả, đích và dấu_thời_gian

Khi kết thúc:
  chặn truy_cập_mới theo lần_cấp
  xử_lý phiên, token và quyền theo cơ_chế tại_đích
  xác_nhận kết_quả hoặc ghi lỗi cần_xử_lý
```

Nếu quyền được truyền đến đích chậm, phải biết thời điểm nào được dùng để tính thời lượng và không để tổng thời gian vượt hạn tuyệt đối. Nếu phê duyệt bị hủy khi hệ thống đang kích hoạt, cần xử lý phần quyền đã được tạo thay vì chỉ đổi trạng thái yêu cầu ở cổng.

### 11.3. Những tình huống biên cần xác định trước

| Tình huống | Kết quả mong muốn trong mô hình này |
| --- | --- |
| 21:59 gửi thao tác quản trị | Chưa thuộc cửa sổ, không được thực hiện |
| 22:12 kích hoạt hợp lệ | Có thể bắt đầu, hạn kết thúc là 22:42 |
| 22:42 gửi thao tác mới theo lần cấp cũ | Không còn hợp lệ theo quy ước biên |
| 22:45 xin kích hoạt bằng phê duyệt ban đầu | Đã qua hạn chót kích hoạt 22:40 |
| Token còn được đích chấp nhận sau 22:42 | Cần xác định khoảng trống thực thi và xử lý theo thiết kế |
| Có vai trò khác vẫn cho cùng hành động | Phải xét quyền hiệu lực từ nguồn đó, không kết luận đã mất toàn bộ quyền |
| Thu hồi chưa được xác nhận tại đích | Giữ trạng thái cần xử lý, không báo đã kết thúc hoàn toàn |

Bảng này mô tả hành vi cần làm rõ trong chính sách. Nó không thay thế việc ánh xạ và xác nhận cơ chế của hệ thống thực tế.

## 12. Quyền theo thời gian cho tài khoản dịch vụ và workload

Workload có thể cần quyền cho một lần chạy, một lịch tác vụ hoặc một giai đoạn triển khai. Nên gắn quyền với danh tính workload, mục đích, tài nguyên và mã lần chạy thay vì chỉ dựa vào việc đồng hồ đã đến một giờ nhất định.

Ví dụ, một pipeline hợp lệ được nhận phương tiện truy cập ngắn hạn trong lúc triển khai ứng dụng A. Bộ cấp cần kiểm tra danh tính và điều kiện của lần chạy; việc hết hạn hoặc gia hạn phải nằm trong chính sách của nhiệm vụ.

Những câu hỏi cần xác định gồm:

- Nếu lần chạy bị hủy, quyền và token được xử lý ra sao?
- Nếu pipeline chạy lại, đó là lần cấp mới hay tiếp tục lần cũ?
- Nếu một lịch chạy bị trễ, có được thực hiện ngoài cửa sổ không?
- Nếu tác vụ đang chạy khi cửa sổ kết thúc, cơ chế hoàn tất an toàn là gì?
- Ai có thể đổi lịch, sửa mã thực thi hoặc mở rộng giới hạn?
- Nếu hệ thống cấp credential lỗi, có tự dùng credential thường trực ngoài kiểm soát không?

Credential ngắn hạn không giải quyết hết nếu workload có thể liên tục xin lại quyền quá rộng mà không kiểm tra nhu cầu và phạm vi. Cơ chế cấp mới và gia hạn quan trọng không kém thời hạn của từng giá trị.

## 13. Bằng chứng, giám sát và kiểm kê

### 13.1. Bằng chứng phải phân biệt kế hoạch và thực tế

| Nhóm | Thông tin cần lưu |
| --- | --- |
| Chính sách dự định | Cửa sổ, múi giờ, thời lượng, hạn kích hoạt và giới hạn tuyệt đối |
| Quyết định | Người hoặc chính sách phê duyệt, phạm vi và lý do |
| Kích hoạt | Thời điểm yêu cầu, thời điểm xác nhận hiệu lực, mã lần cấp |
| Sử dụng | Danh tính, hành động, tài nguyên, kết quả và mã phiên hoặc lần chạy |
| Gia hạn, hủy | Lý do, người quyết định, mốc trước và sau |
| Kết thúc | Hạn theo chính sách, thao tác thu hồi, thời điểm xác nhận và lỗi còn tồn tại |
| Khoảng trống | Độ trễ, lỗi đồng bộ, mất log hoặc hạn chế cơ chế đích |

Không ghi mật khẩu, khóa hay token vào bằng chứng. Có thể dùng định danh credential và tham chiếu quản lý để liên kết mà không sao chép bí mật.

### 13.2. Những tín hiệu cần theo dõi

Các tín hiệu có ích gồm quyền quá hạn chưa xác nhận thu hồi, truy cập ngoài cửa sổ, gia hạn liên tiếp, credential có thời hạn dài hơn quyền, lịch thay đổi bất thường và nguồn quyền thường trực làm vô hiệu hóa mục tiêu giới hạn thời gian.

Cần đối chiếu nguồn tại PAM, vault, hệ thống danh tính và đích khi có thể. Một cổng báo “expired” nhưng đích vẫn ghi thao tác thành công là dữ liệu cần điều tra, không phải hai bản ghi có thể bỏ qua vì đã đóng yêu cầu.

Giảm thời gian quyền hoạt động là một cải thiện có thể đo, nhưng không tự quy đổi thành một tỷ lệ giảm rủi ro cố định. Mức tác động còn phụ thuộc vào quyền, tài nguyên, danh tính và chất lượng thực thi.

## 14. Sai lầm thường gặp

| Nhầm lẫn | Cách hiểu cần dùng |
| --- | --- |
| Có thời hạn trong ticket là đủ | Phải có cơ chế thực thi và xác nhận tại lớp liên quan |
| Chỉ cho đăng nhập trong giờ làm là đã least privilege | Vẫn cần giới hạn hành động, tài nguyên và nhu cầu thực tế |
| Hết hạn vai trò là mọi phiên kết thúc | Kiểm tra token, cache, phiên và cơ chế thu hồi của đích |
| Idle timeout thay được hạn kết thúc cố định | Hoạt động liên tục có thể tránh idle timeout |
| Token ngắn hạn luôn có nghĩa quyền ngắn hạn | Việc cấp lại và nguồn quyền thường trực cũng phải kiểm soát |
| Có tác vụ gỡ nhóm theo lịch thì không thể quá hạn | Tác vụ có thể lỗi; cần đối chiếu và xử lý trạng thái tồn dư |
| Mọi giờ địa phương đều có thể đổi bằng một độ lệch cố định | Lịch vùng và mốc tuyệt đối có ngữ nghĩa khác nhau |
| Hết một bản cấp thì chắc chắn mất khả năng thực hiện | Cần xét mọi nguồn quyền còn hiệu lực |
| Gia hạn là tiếp tục kỹ thuật, không cần quyết định | Gia hạn thay đổi thời gian đặc quyền được phép tồn tại |
| Hết hạn sẽ tự hoàn tác hành động đã làm | Thay đổi và tác vụ đã khởi chạy cần chính sách xử lý riêng |

## 15. Bài tập vận dụng

Một nhóm cấp vai trò quản trị từ 22:00 đến 23:00 bằng tác vụ lịch. Người dùng nhận token lúc 22:55 có thể dùng đến 00:55. Quyết định cho phép được cache 20 phút. Một số người còn có quyền tương đương qua nhóm thường trực. Lịch không ghi múi giờ và tác vụ gỡ quyền đôi khi thất bại.

Hãy phân tích:

1. Những lớp nào có thời hạn không khớp nhau?
2. Vì sao lịch gán vai trò chưa đủ thực thi cửa sổ 22:00–23:00?
3. Cần định nghĩa lại cách cấp token và dùng cache như thế nào?
4. Quyền từ nhóm thường trực ảnh hưởng đến kết luận thu hồi ra sao?
5. Những mốc thời gian và bằng chứng nào cần bổ sung?
6. Nếu một tác vụ hợp lệ đang chạy lúc 23:00, cần có quyết định thiết kế nào trước khi vận hành?

**Định hướng trả lời:** phải giới hạn khả năng sử dụng tại lớp thực thi, xử lý thời hạn phương tiện và cache, đối chiếu nguồn quyền khác và xác định múi giờ rõ ràng. Lưu cả thời điểm hết hạn theo chính sách lẫn xác nhận thu hồi. Với tác vụ dài, cần cơ chế dừng, hoàn tất an toàn hoặc gia hạn có thẩm quyền; không để phần này được quyết định ngầm bởi một phiên còn mở.

## 16. Ghi nhớ

Permission theo thời gian là một điều kiện phân quyền phải được mô tả và thực thi rõ ràng. Nó bao gồm thời điểm bắt đầu, kết thúc, lịch, thời lượng và cách xử lý những thay đổi trong vòng đời nhiệm vụ.

Trong PAM, hãy kiểm tra toàn bộ chuỗi từ phê duyệt đến quyền tại đích, credential, token, phiên và bằng chứng thu hồi. Kết hợp giới hạn thời gian với least privilege và JEA giúp quyền chỉ có hiệu lực trong phạm vi thực sự cần, thay vì chỉ có một ngày hết hạn trên giao diện.