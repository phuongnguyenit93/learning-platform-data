# Emergency privileged identity

## 1. Mục tiêu và bối cảnh

Trong chương **Danh tính đặc quyền**, *emergency privileged identity* là danh tính được chuẩn bị để thực hiện những thao tác đặc quyền cần thiết trong tình huống khẩn cấp, khi đường quản trị thông thường không sử dụng được hoặc không còn đủ tin cậy. Cơ chế truy cập này thường được gọi là **break-glass access**.

PAM cần vừa kiểm soát chặt quyền quản trị, vừa giữ được khả năng phục hồi khi hệ thống danh tính, vault, cổng truy cập hoặc quy trình phê duyệt gặp sự cố. Nếu toàn bộ khả năng sửa một hệ thống đều phụ thuộc vào chính hệ thống đang hỏng, tổ chức có thể tự khóa mất đường phục hồi.

Sau bài học, bạn có thể:

- Phân biệt danh tính khẩn cấp, credential khẩn cấp và quy trình break-glass.
- Xác định khi nào được sử dụng, ai chịu trách nhiệm và cần quyền đến đâu.
- Kiểm tra các phụ thuộc có thể làm mất đường truy cập dự phòng.
- Thiết kế lưu giữ credential, giám sát, thu hồi và xử lý sau sử dụng.
- Lập bằng chứng phục vụ kiểm toán và điều tra sự cố mà không làm lộ bí mật.

## 2. Danh tính đặc quyền khẩn cấp là gì?

**Emergency privileged identity** là danh tính có phạm vi quyền được xác định trước nhằm khôi phục khả năng quản trị hoặc xử lý một tình huống khẩn cấp theo chính sách. Nó có thể được biểu diễn bằng một tài khoản riêng, một vai trò khẩn cấp hoặc một cơ chế danh tính khác mà nền tảng hỗ trợ.

Cần tách ba thành phần:

| Thành phần | Vai trò | Ví dụ ở mức khái niệm |
| --- | --- | --- |
| Danh tính | Chủ thể được hệ thống nhận diện và gắn quyền | Tài khoản phục hồi dành cho một miền quản trị |
| Credential hoặc phương thức xác thực | Phương tiện chứng minh quyền sử dụng danh tính | Bí mật được bảo quản riêng hoặc phương tiện xác thực phần cứng |
| Quy trình break-glass | Quy tắc quyết định, sử dụng, giám sát và kết thúc truy cập | Kích hoạt theo sự cố, lưu người nhận credential, rà soát sau sử dụng |

Có một mật khẩu dự phòng chưa tạo thành một cơ chế break-glass hoàn chỉnh. Còn phải biết ai được sử dụng, dùng vào việc gì, bằng đường nào, phạm vi quyền thực tế và cách khôi phục trạng thái an toàn sau sự kiện.

Ngược lại, một tài khoản có tên “emergency” nhưng thường xuyên dùng để vận hành vẫn đang hoạt động như một tài khoản quản trị thường ngày. Mục đích và hành vi sử dụng quan trọng hơn tên gọi.

### 2.1. Quan hệ với tài khoản quản trị thông thường

| Khía cạnh | Danh tính quản trị thông thường | Danh tính khẩn cấp |
| --- | --- | --- |
| Nhu cầu | Công việc quản trị đã định | Phục hồi hoặc xử lý tình huống khẩn cấp được xác định |
| Đường truy cập | Qua các cơ chế PAM vận hành bình thường | Qua đường đã chuẩn bị cho các kiểu sự cố cụ thể |
| Tần suất sử dụng | Theo nhiệm vụ hợp lệ | Hiếm, có lý do và được rà soát |
| Quyền | Giới hạn theo nhiệm vụ, có thể JIT/JEA | Giới hạn theo mục tiêu phục hồi; có thể cần quyền rộng trong một miền |
| Giám sát | Theo chính sách vận hành | Cần nhận diện rõ mọi lần sử dụng và xử lý cả khi giám sát chính gặp lỗi |
| Kết thúc | Theo vòng đời nhiệm vụ | Kết thúc truy cập, xử lý credential, đối chiếu thay đổi và khôi phục dự phòng |

Tài khoản quản trị tích hợp sẵn không tự động là danh tính khẩn cấp được quản lý. Nếu chọn sử dụng một tài khoản như vậy cho phục hồi, vẫn cần kiểm kê quyền, chủ sở hữu, phương thức xác thực và quy trình tương ứng.

### 2.2. Hai tình huống phải phân biệt

- **Hệ thống quản trị bị gián đoạn:** cần khôi phục dịch vụ xác thực, đường mạng, vault hoặc cấu hình sai.
- **Hệ thống quản trị bị nghi xâm nhập:** cần một đường thực thi và nguồn tin cậy phù hợp để tránh tiếp tục dựa vào thành phần đã bị kiểm soát.

Một đường dự phòng đủ cho sự cố mất kết nối chưa chắc phù hợp khi chính nhà cung cấp danh tính, máy trạm quản trị hoặc vault đã bị chiếm quyền. Thiết kế phải nêu rõ tình huống nó bảo vệ và những giả định còn cần đúng.

## 3. Khi nào được sử dụng?

Tiêu chí sử dụng cần được xác định trước, gắn với mức độ ảnh hưởng và trạng thái của đường quản trị thông thường.

Ví dụ phù hợp tùy phạm vi được duyệt:

- Chính sách xác thực bị cấu hình sai làm quản trị viên hợp lệ không thể đăng nhập.
- Thành phần PAM hoặc dịch vụ liên kết danh tính không hoạt động, trong khi cần khôi phục một hệ thống thiết yếu.
- Credential quản trị thông thường bị nghi lộ và cần cô lập, thu hồi hoặc phục hồi quyền kiểm soát.
- Cơ chế cấp quyền có thời hạn không hoạt động, khiến tác vụ phục hồi khẩn cấp không thể thực hiện theo đường thường lệ.

Việc dùng break-glass không nên dựa đơn thuần vào cảm giác “làm cách này nhanh hơn”. Một công việc quản trị thông thường, một yêu cầu chưa được duyệt hoặc nhu cầu né giới hạn quyền cần được xử lý bằng quy trình phù hợp của công việc đó.

Mỗi lần sử dụng cần trả lời được:

1. Sự cố nào đang xảy ra và tác động là gì?
2. Vì sao đường quản trị thông thường không sử dụng được hoặc không đáng tin?
3. Cần phục hồi khả năng nào, trên tài nguyên nào?
4. Ai quyết định sử dụng, ai thực hiện và ai sẽ rà soát?
5. Điều kiện nào đánh dấu hoàn thành và kết thúc truy cập?

Nếu tình huống không cho phép chờ đủ các bước phê duyệt thường lệ, chính sách cần quy định trước thẩm quyền ra quyết định và cách ghi nhận ngoại lệ. Không nên đợi đến khi hệ thống phê duyệt đã hỏng mới quyết định ai được phép dùng đường khẩn cấp.

## 4. Thiết kế quyền theo mục tiêu phục hồi

### 4.1. Xác định miền quản trị và chức năng cần có

Least privilege vẫn áp dụng cho danh tính khẩn cấp. Tuy nhiên, một nhiệm vụ phục hồi hệ thống danh tính có thể cần quyền mạnh hơn một tác vụ vận hành nhỏ. Điều cần làm là giải thích quyền đó phục vụ mục tiêu gì và giới hạn nó trong miền phù hợp.

Ví dụ:

| Mục tiêu phục hồi | Quyền có thể cần theo thiết kế | Phạm vi cần ràng buộc |
| --- | --- | --- |
| Sửa chính sách gây khóa truy cập | Đọc và sửa chính sách liên quan | Đúng miền danh tính hoặc tenant được giao |
| Khôi phục kết nối quản trị | Thay đổi cấu hình mạng quản trị | Thiết bị và phân vùng cần phục hồi |
| Khôi phục dịch vụ vault | Thao tác phục hồi dịch vụ hoặc dữ liệu được phép | Cụm vault và môi trường xác định |
| Thu hồi credential bị lộ | Vô hiệu hóa hoặc thay credential liên quan | Những danh tính và đích bị ảnh hưởng |

Đây là ví dụ để phân tích nhu cầu, không phải tập quyền mặc định có thể áp dụng cho mọi sản phẩm. Quyền thực tế phải ánh xạ sang mô hình phân quyền và khả năng phục hồi của nền tảng.

### 4.2. Không gom mọi miền vào một danh tính duy nhất

Một danh tính khẩn cấp có khả năng quản trị đồng thời môi trường thử nghiệm, sản xuất, kho bí mật và hệ thống log sẽ có phạm vi ảnh hưởng rất lớn nếu bị lộ.

Nên xem xét tách theo ranh giới tin cậy, môi trường và mục tiêu phục hồi. Số lượng danh tính phải cân bằng giữa phạm vi ảnh hưởng và khả năng quản lý; không nên đặt một con số cố định cho mọi tổ chức mà bỏ qua kiến trúc thực tế.

Quyền hiệu lực phải được kiểm tra từ nguồn cấp quyền thực tế, bao gồm nhóm, vai trò và chính sách kế thừa. Đổi nhãn hoặc chuyển credential sang một nơi lưu khác không làm giảm quyền của danh tính.

### 4.3. JIT và quyền thường trực trong đường khẩn cấp

Nếu cơ chế JIT còn hoạt động và không nằm trong miền bị sự cố, có thể dùng nó để giới hạn thời gian quyền khẩn cấp. Nhưng nếu JIT phụ thuộc vào chính thành phần cần phục hồi, nó có thể không dùng được trong tình huống dự kiến.

Một số thiết kế vì vậy cần giữ sẵn một danh tính có quyền phục hồi. Đây là ngoại lệ cần được quản lý rõ: phạm vi hẹp nhất đáp ứng mục tiêu, credential được bảo vệ, mọi lần sử dụng được nhận diện, tư cách người giữ được rà soát và khả năng sử dụng được kiểm tra định kỳ.

Không thể mặc định “khóa tài khoản khi không dùng” là phù hợp với mọi trường hợp. Nếu việc mở khóa lại phụ thuộc vào hệ thống đã hỏng, thao tác đó làm mất mục đích dự phòng. Cần phân biệt trạng thái tồn tại của danh tính, trạng thái quyền và khả năng nhận hoặc sử dụng phương tiện xác thực.

## 5. Kiểm tra phụ thuộc: đường dự phòng có thật sự dùng được?

### 5.1. Nhận diện vòng phụ thuộc

Một vòng phụ thuộc thường gặp là:

```text
Muốn sửa hệ thống danh tính
    -> phải đăng nhập cổng PAM
    -> cổng PAM cần hệ thống danh tính đang hỏng

Muốn sửa vault
    -> cần credential phục hồi
    -> credential chỉ nằm trong vault đang hỏng
```

Một tài khoản riêng vẫn có thể mắc cùng vòng phụ thuộc nếu nó dùng cùng dịch vụ xác thực, cùng chính sách lỗi, cùng đường mạng hoặc cùng thiết bị truy cập.

### 5.2. Lập bảng phụ thuộc theo tình huống

| Thành phần | Câu hỏi cần đặt ra |
| --- | --- |
| Xác thực và liên kết danh tính | Khi IdP hoặc liên kết bị lỗi, đường khẩn cấp còn xác thực được không? |
| Xác thực bổ sung | Phương tiện thay thế có phụ thuộc vào cùng dịch vụ đang gián đoạn không? |
| Kho credential | Nếu vault chính không dùng được, có cách nhận credential hợp lệ khác đã được bảo vệ không? |
| Mạng và điểm vào quản trị | Có đến được hệ thống đích mà không đi qua thành phần đang lỗi không? |
| Tài liệu và danh sách liên hệ | Có đọc được khi cổng nội bộ hoặc đăng nhập thông thường bị gián đoạn không? |
| Phê duyệt và thông báo | Có người có thẩm quyền và kênh thay thế khi hệ thống chính không hoạt động không? |
| Thiết bị thực thi | Có máy trạm hoặc điểm truy cập đủ tin cậy cho loại sự cố đó không? |
| Hệ thống đích | Nó còn hoạt động và hỗ trợ cách xác thực dự phòng đã chọn không? |
| Bằng chứng | Có thể ghi nhận hoạt động và chuyển lưu sau sự cố như thế nào? |

Mục tiêu là độc lập với **những phụ thuộc được giả định sẽ hỏng**. Không có nghĩa phải bỏ mọi lớp kiểm soát hoặc có thể hoạt động khi toàn bộ hạ tầng đều ngừng. Nếu hệ thống đích không còn chạy hoặc nền tảng bên dưới không hỗ trợ truy cập, một danh tính dự phòng riêng không tự khôi phục được nó.

### 5.3. Độc lập không đồng nghĩa bỏ xác thực mạnh

Không nên mặc định danh tính khẩn cấp phải tắt MFA hoặc loại bỏ mọi điều kiện xác thực. Có thể chọn phương thức xác thực mạnh có miền lỗi phù hợp, phương tiện dự phòng được quản lý hoặc cơ chế phục hồi mà nền tảng hỗ trợ.

Nếu một điều kiện truy cập thông thường có thể tự khóa mất đường phục hồi, cần thiết kế ngoại lệ cụ thể và bù bằng các kiểm soát phù hợp. Ngoại lệ phải có phạm vi, lý do, người chịu trách nhiệm và cách giám sát; tránh một danh tính được miễn mọi điều kiện mà không ai giải thích được vì sao.

Cũng cần kiểm tra ai có khả năng sửa hoặc vô hiệu hóa đường khẩn cấp. Nếu mọi người quản trị thông thường đều có thể làm hỏng nó mà không phát hiện được, tính độc lập mong muốn có thể không tồn tại.

## 6. Chủ sở hữu, người giữ và trách nhiệm sử dụng

Một mô hình trách nhiệm có thể phân biệt:

| Vai trò | Trách nhiệm |
| --- | --- |
| Chủ sở hữu danh tính | Xác nhận mục đích, phạm vi quyền, vòng đời và nhu cầu duy trì |
| Người bảo quản phương tiện xác thực | Bảo vệ, bàn giao và kiểm tra tình trạng credential hoặc thiết bị xác thực |
| Người có thẩm quyền quyết định | Xác định tình huống đáp ứng điều kiện sử dụng khẩn cấp |
| Người thực hiện | Sử dụng quyền theo mục tiêu, ghi nhận hoạt động và kết thúc đúng quy trình |
| Người giám sát hoặc rà soát | Đối chiếu sử dụng thực tế với quyết định và xác nhận xử lý sau sự kiện |

Một tổ chức nhỏ có thể không có người riêng cho mọi vai trò. Khi có vai trò kiêm nhiệm, cần ghi rõ trách nhiệm và bố trí việc rà soát phù hợp với mức độ tác động.

Tách trách nhiệm hoặc yêu cầu nhiều người tham gia có thể giảm nguy cơ một cá nhân tự lấy credential và che giấu sử dụng. Tuy nhiên, cần bảo đảm người được giao có thể thực sự tham gia khi khẩn cấp. Nếu áp dụng cơ chế đồng kiểm soát, phải kiểm tra cả khả năng phối hợp ngoài giờ hoặc khi một địa điểm không dùng được.

Với danh tính dùng chung ở đích, chuỗi quy trách nhiệm cần nối người nhận phương tiện xác thực, thời điểm nhận, phiên sử dụng và mã sự cố. Chỉ thấy tên tài khoản khẩn cấp trong log chưa xác định được người thực hiện.

## 7. Bảo quản credential và phương tiện xác thực

### 7.1. Các thuộc tính cần đạt

Credential cần đủ mạnh, riêng biệt cho phạm vi được giao và được bảo quản bằng cơ chế phù hợp. Không tái sử dụng cùng một bí mật cho nhiều miền phục hồi độc lập.

Cách lưu giữ có thể bao gồm kho bảo mật với đường dự phòng phù hợp, phương tiện xác thực phần cứng hoặc cơ chế bảo quản ngoại tuyến được quản lý. Việc chọn cách nào phải dựa trên nền tảng và các kiểu sự cố cần chịu được.

Dù chọn cách nào, cần xác định:

- Ai được nhận, kiểm tra hoặc thay phương tiện xác thực.
- Làm thế nào để biết đã có người truy xuất hoặc sử dụng.
- Bản dự phòng có còn tương ứng với trạng thái hiện tại ở hệ thống đích không.
- Khi một nơi lưu hoặc một phương tiện bị mất, có đường thay thế nào còn dùng được.
- Làm thế nào để cập nhật mà không vô tình mất mọi đường phục hồi hợp lệ.

Không ghi giá trị bí mật vào tài liệu vận hành, ticket, tin nhắn sự cố hoặc báo cáo kiểm toán. Những nơi đó chỉ nên chứa định danh phương tiện, vị trí quản lý theo chính sách và bằng chứng bàn giao cần thiết.

### 7.2. Tránh bản sao không kiểm soát

Một người lấy credential rồi lưu thêm vào máy cá nhân sẽ làm mất khả năng biết ai còn giữ bí mật. Bản in hoặc bản sao ngoại tuyến cũng cần được kiểm kê và quản lý trạng thái, thay vì được coi là an toàn chỉ vì không kết nối mạng.

Nếu thay credential ở hệ thống đích nhưng quên cập nhật bản dự phòng, đường khẩn cấp có thể thất bại đúng lúc cần dùng. Nếu chỉ cập nhật bản dự phòng mà chưa thay ở đích, tài liệu quản lý lại mô tả sai trạng thái thực tế.

Việc cập nhật cần có bước xác nhận tương ứng giữa phương tiện được bảo quản và hệ thống đích, không để lộ giá trị xác thực trong bằng chứng.

### 7.3. Hết hạn và thay đổi người giữ

Credential, chứng thư hoặc thiết bị xác thực có thể hết hạn, hỏng hoặc bị thu hồi. Người giữ cũng có thể đổi nhiệm vụ hoặc rời tổ chức. Vì vậy, vòng đời danh tính khẩn cấp phải theo dõi cả quyền, phương thức xác thực và người chịu trách nhiệm.

Không nên áp dụng một chính sách hết hạn mà không có người cập nhật và kiểm tra đường dự phòng. Đồng thời, nhu cầu duy trì khả năng phục hồi không phải lý do để bỏ qua credential đã lộ, phương tiện bị mất hoặc quyền của người đã rời vai trò.

## 8. Quy trình sử dụng trong một sự cố

### 8.1. Bước 1 — Xác nhận tình huống và mục tiêu

Người có thẩm quyền ghi nhận mã sự cố, phạm vi ảnh hưởng, lý do không dùng được đường thông thường và kết quả cần đạt. Nếu hệ thống ghi nhận chính không dùng được, sử dụng cách ghi nhận thay thế đã chuẩn bị, rồi đối chiếu lại khi khôi phục.

Thời gian và nguồn thông tin cần được ghi rõ. Bản ghi thủ công không nên tạo cảm giác chính xác tuyệt đối nếu đồng hồ hoặc thời điểm sự kiện chưa được xác minh.

### 8.2. Bước 2 — Nhận phương tiện và chuẩn bị điểm truy cập

Người được chỉ định nhận phương tiện xác thực qua cơ chế đã quy định. Bằng chứng cần ghi ai nhận, thời điểm và mục đích, không ghi giá trị bí mật.

Điểm truy cập phải phù hợp với loại sự cố. Nếu máy trạm hoặc hệ thống danh tính thông thường bị nghi xâm nhập, việc dùng credential khẩn cấp trên cùng môi trường chưa được đánh giá có thể làm lộ luôn đường phục hồi.

### 8.3. Bước 3 — Thực hiện trong phạm vi cần thiết

Người thực hiện chỉ làm những thay đổi cần cho mục tiêu phục hồi hoặc ứng phó đã được quyết định. Khi có thay đổi đáng kể về phạm vi, cần ghi nhận và thực hiện theo thẩm quyền xử lý sự cố tương ứng.

Ưu tiên các thao tác có thể giải thích, đối chiếu và kiểm tra kết quả. Không tận dụng phiên khẩn cấp để xử lý công việc thường lệ không liên quan. Nếu nền tảng hỗ trợ giới hạn thời gian hoặc phiên mà không làm mất khả năng phục hồi, nên sử dụng giới hạn phù hợp.

### 8.4. Bước 4 — Xác nhận phục hồi và kết thúc sử dụng

Cần kiểm tra dịch vụ hoặc đường quản trị thông thường đã hoạt động theo yêu cầu. Kết thúc phiên khẩn cấp, ngừng các khả năng truy cập tạm thời và ghi lại những thay đổi đã tạo.

Đóng cửa sổ trình duyệt không bảo đảm mọi token, phiên từ xa hoặc kết nối đã chấm dứt. Cách kết thúc phải dựa vào cơ chế thực tế của nền tảng.

### 8.5. Bước 5 — Xử lý sau sử dụng

Sau sự kiện, cần:

- Đối chiếu hành động thực tế với mục tiêu và thẩm quyền được ghi nhận.
- Rà soát thay đổi quyền, cấu hình, tài khoản, khóa hoặc phương thức xác thực phát sinh.
- Thay hoặc thu hồi credential, token và phương tiện liên quan theo chính sách và tình trạng phơi lộ.
- Xử lý các phiên còn tồn tại và kiểm tra đường truy cập không mong muốn.
- Cập nhật nơi bảo quản và xác nhận đường khẩn cấp hợp lệ cho lần sau.
- Lưu bằng chứng và giải quyết những điểm thiếu hoặc sai lệch đã phát hiện.

Với mật khẩu dùng chung được tiết lộ cho người thực hiện, cần có kế hoạch thay bí mật sau sử dụng. Với cơ chế phần cứng hoặc credential ngắn hạn, xử lý sau sử dụng phải phù hợp với loại phương tiện và sự kiện thực tế; không thể áp dụng một thao tác “đổi mật khẩu” cho mọi trường hợp.

Tránh vô hiệu hóa hoặc xóa đường phục hồi cuối cùng khi chưa xác nhận đường quản trị và dự phòng thay thế. Cũng không giữ vô hạn quyền tạm thời chỉ vì sự cố đã kết thúc.

## 9. Ví dụ xuyên suốt: chính sách IdP gây khóa truy cập

### 9.1. Bối cảnh

Một thay đổi chính sách khiến quản trị viên không đăng nhập được qua IdP. Cổng PAM cũng dùng IdP đó. Hệ thống đích còn hoạt động, nhưng mọi đường quản trị thông thường đều phụ thuộc vào chính sách bị lỗi.

Tổ chức đã chuẩn bị một danh tính phục hồi trong miền quản trị liên quan, với phương thức xác thực không phụ thuộc vào thành phần liên kết đang hỏng và được nền tảng đích hỗ trợ. Credential hoặc phương tiện xác thực được bảo quản theo quy trình riêng đã kiểm tra.

### 9.2. Cách xử lý theo thiết kế

| Giai đoạn | Việc cần làm | Bằng chứng |
| --- | --- | --- |
| Xác nhận | Kiểm tra phạm vi khóa và quyết định dùng đường khẩn cấp | Mã sự cố, người quyết định, mục tiêu |
| Truy xuất | Người được giao nhận phương tiện theo cơ chế dự phòng | Người nhận, thời gian, định danh phương tiện |
| Truy cập | Sử dụng điểm quản trị phù hợp và đường đã chuẩn bị | Danh tính ở đích, nguồn truy cập, thời gian |
| Phục hồi | Kiểm tra và sửa đúng chính sách gây khóa | Thay đổi trước và sau, kết quả thực hiện |
| Xác minh | Thử đường quản trị thông thường theo phạm vi được phép | Kết quả xác nhận phục hồi |
| Kết thúc | Đóng phiên, xử lý phương tiện và rà soát thay đổi | Kết quả thu hồi, cập nhật bảo quản, người rà soát |

Điểm quyết định là đường phục hồi đã được chuẩn bị và không cùng phụ thuộc vào thành phần bị lỗi. Nếu danh tính dự phòng vẫn phải đăng nhập qua chính IdP đang khóa, việc tạo thêm tài khoản không giải quyết được tình huống này.

### 9.3. Nếu IdP bị nghi xâm nhập

Khi có dấu hiệu IdP đã bị kiểm soát, việc chỉ sửa chính sách để đăng nhập lại chưa đủ. Cần đánh giá nguồn tin cậy dùng cho phục hồi, các phương tiện xác thực có thể đã bị lộ và những thay đổi quyền do bên tấn công tạo ra.

Tùy phạm vi sự cố, có thể phải phối hợp thu hồi phiên, xử lý credential và phục hồi cấu hình từ nguồn đã xác minh. Danh tính khẩn cấp là một khả năng thực thi trong kế hoạch ứng phó; nó không tự bảo đảm toàn bộ môi trường đã sạch sau khi đăng nhập thành công.

## 10. Giám sát khi hệ thống chính cũng đang lỗi

Mọi lần sử dụng danh tính khẩn cấp đều cần được nhận diện. Cảnh báo có thể dựa vào truy xuất phương tiện xác thực, đăng nhập, hành động nhạy cảm, thay đổi quyền hoặc thay đổi chính danh tính khẩn cấp.

Tuy nhiên, kênh cảnh báo dùng cùng hệ thống đang gián đoạn có thể không hoạt động. Cần xác định cách phát hiện và ghi nhận thay thế phù hợp với tình huống dự kiến, chẳng hạn log tại đích, kênh thông báo độc lập hoặc ghi nhận có kiểm soát trong lúc chờ hệ thống thu thập phục hồi.

Khi khôi phục, cần đối chiếu các nguồn bằng chứng và nêu rõ khoảng trống quan sát nếu có. Không nên kết luận “không có hoạt động” chỉ vì hệ thống thu thập log đã ngừng trong thời gian đó.

Một bộ bằng chứng nên liên kết được:

```text
Mã sự cố
  -> quyết định sử dụng
  -> người nhận phương tiện xác thực
  -> danh tính và phiên tại đích
  -> hành động, tài nguyên, kết quả
  -> kết thúc phiên và xử lý credential
  -> rà soát và xác nhận khả năng phục hồi lần sau
```

Log và bản ghi phiên cần được bảo vệ để người dùng đặc quyền không thể tùy ý xóa toàn bộ dấu vết mà không bị phát hiện. Mức độ độc lập, khả năng chống sửa và giới hạn của từng nguồn bằng chứng phải được hiểu rõ; không thể mặc định một nơi lưu log là bất biến.

## 11. Kiểm kê và diễn tập khả năng phục hồi

### 11.1. Bản ghi kiểm kê tối thiểu

| Trường | Nội dung |
| --- | --- |
| Định danh và miền | Danh tính thuộc hệ thống, môi trường và ranh giới tin cậy nào |
| Mục tiêu | Những tình huống được phép sử dụng |
| Quyền hiệu lực | Chức năng phục hồi, nguồn quyền và phạm vi tài nguyên |
| Chủ sở hữu | Người chịu trách nhiệm duy trì nhu cầu và khả năng sử dụng |
| Người giữ | Ai quản lý phương tiện, cơ chế thay thế và bàn giao |
| Phụ thuộc | Xác thực, mạng, vault, thiết bị, tài liệu và kênh quyết định |
| Phương thức xác thực | Loại phương tiện và tham chiếu quản lý; không ghi bí mật |
| Giám sát | Sự kiện cần cảnh báo, nơi nhận và phương án khi kênh chính lỗi |
| Vòng đời | Hết hạn, thay đổi phương tiện, thay đổi người giữ và thu hồi |
| Kiểm tra | Lần kiểm tra gần nhất, kết quả, lỗi tồn tại và người xử lý |

### 11.2. Diễn tập phải kiểm tra đường sử dụng thực tế

Một lần đăng nhập thử khi mọi hệ thống đang hoạt động chỉ chứng minh được một phần. Cần kiểm tra các giả định liên quan đến kiểu sự cố: có đọc được hướng dẫn, liên hệ đúng người, nhận được phương tiện, đến được đích và thực hiện chức năng phục hồi hay không.

Nội dung diễn tập cần phù hợp với môi trường và được kiểm soát để không tự gây sự cố. Có thể kết hợp kiểm tra tài liệu, mô phỏng và thử nghiệm có phạm vi; không cần gây mất dịch vụ sản xuất để chứng minh mọi giả định.

Sau diễn tập, cần xác nhận phương tiện dự phòng vẫn hợp lệ, không để lại phiên hoặc quyền tạm thời, đồng thời xử lý thông tin bí mật đã được tiếp xúc theo quy trình.

Tần suất kiểm tra nên dựa trên mức độ quan trọng và thay đổi của hệ thống. Những thay đổi như thay IdP, sửa chính sách truy cập, đổi mạng quản trị, thay vault hoặc thay người giữ đều có thể làm mất hiệu lực của kết quả kiểm tra cũ.

## 12. Sai lầm thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Chỉ chuẩn bị một mật khẩu trong tài liệu | Lộ bí mật, thiếu trách nhiệm và không biết còn dùng được không | Quản lý cả danh tính, phương tiện và quy trình |
| Mọi thứ vẫn phụ thuộc vào IdP hoặc vault chính | Không truy cập được khi đúng thành phần đó hỏng | Kiểm tra miền lỗi và đường dự phòng theo tình huống |
| Mặc định tắt mọi lớp xác thực | Đường phục hồi trở thành điểm truy cập yếu | Dùng phương thức phù hợp và ngoại lệ có phạm vi rõ |
| Một danh tính quản trị mọi môi trường | Credential bị lộ có phạm vi ảnh hưởng rất lớn | Tách theo ranh giới tin cậy và nhu cầu phục hồi |
| Sử dụng thường xuyên vì tiện | Mất ý nghĩa khẩn cấp, tăng phơi lộ và khó rà soát | Sửa quy trình vận hành thường lệ và theo dõi mọi lần sử dụng |
| Credential ở đích và bản dự phòng lệch nhau | Đăng nhập thất bại khi cần phục hồi | Cập nhật và xác nhận tương ứng có kiểm soát |
| Không có người giữ thay thế phù hợp | Có phương tiện nhưng không thể nhận khi khẩn cấp | Chuẩn bị vai trò, khả năng phối hợp và phương án thay thế |
| Kết thúc sự cố nhưng không xử lý phiên và quyền | Đường truy cập tạm thời tiếp tục tồn tại | Xác nhận kết thúc, rà soát thay đổi và xử lý credential |
| Dọn dẹp bằng cách xóa luôn đường phục hồi cuối | Mất khả năng ứng phó cho sự cố tiếp theo | Xác nhận các đường hợp lệ trước khi thay đổi hoặc loại bỏ |
| Chỉ dựa vào log trung tâm đang lỗi | Khoảng trống bằng chứng bị hiểu nhầm là không có hoạt động | Chuẩn bị nguồn thay thế và đối chiếu sau khôi phục |

## 13. Bài tập vận dụng

Một tổ chức có tài khoản tên `emergency-admin`. Tài khoản này đăng nhập qua cùng IdP với quản trị viên thường, mật khẩu chỉ nằm trong vault cần IdP để mở. Nhóm trực ca dùng tài khoản đó hằng tuần vì nhanh hơn việc xin quyền. Sau mỗi lần dùng, không ai kiểm tra phiên còn tồn tại hay các thay đổi quyền đã tạo.

Hãy phân tích:

1. Những điểm nào khiến đường này không đáp ứng mục tiêu phục hồi khi IdP gặp lỗi?
2. Vì sao tên tài khoản không chứng minh được đây là danh tính khẩn cấp được quản lý?
3. Cần tách những trách nhiệm và bổ sung bằng chứng nào?
4. Làm thế nào để xử lý nhu cầu vận hành hằng tuần mà không tiếp tục dựa vào break-glass?
5. Những kiểm tra nào cần có trước khi thay đổi phương thức xác thực hoặc nơi lưu credential?

**Định hướng trả lời:** cần loại bỏ vòng phụ thuộc trong phạm vi tình huống cần chịu được, xác định mục tiêu và quyền phục hồi, quản lý người giữ và mọi lần sử dụng. Công việc hằng tuần nên được thiết kế thành nhiệm vụ quản trị thông thường với quyền tối thiểu và JIT/JEA phù hợp. Việc chuyển đổi phải xác nhận đường thay thế hoạt động trước khi bỏ đường cũ; sau sử dụng phải kiểm tra phiên, quyền phát sinh và trạng thái phương tiện dự phòng.

## 14. Ghi nhớ

Emergency privileged identity là một phần của khả năng phục hồi quyền kiểm soát. Nó cần được chuẩn bị trước, giới hạn theo mục tiêu, bảo vệ phương tiện xác thực và kiểm tra trước các phụ thuộc có thể thất bại.

Một thiết kế có thể vận hành được phải trả lời đồng thời ba câu hỏi: **có truy cập được trong tình huống đã dự kiến không, có kiểm soát và truy vết được việc sử dụng không, và có khôi phục trạng thái an toàn sau đó không**. Câu trả lời cần bao gồm cả tài khoản, quyền, credential, phiên, người chịu trách nhiệm và bằng chứng.