# MFA coverage

## 1. MFA coverage trả lời câu hỏi gì trong PAM?

Trong quản lý truy cập đặc quyền, **MFA coverage** là mức độ bao phủ của xác thực đa yếu tố đối với tập danh tính hoặc đường truy cập đặc quyền đã xác định. Một chỉ số có ý nghĩa phải trả lời được: ai có thể nhận quyền quản trị, qua những đường nào, và các đường đó có thực sự buộc người truy cập đáp ứng yêu cầu MFA hay không.

Giả sử tất cả quản trị viên đều đã đăng ký ứng dụng xác thực. Cổng PAM yêu cầu MFA, nhưng một số máy chủ vẫn cho phép tài khoản quản trị đăng nhập trực tiếp bằng mật khẩu. Tỷ lệ đăng ký MFA có thể đạt 100%, trong khi việc thực thi bảo vệ truy cập đặc quyền vẫn còn lỗ hổng. Vì vậy, cần gắn tên chỉ số với đúng điều đã đo: đăng ký, cấu hình chính sách, thực thi được xác minh, hay mức bảo đảm của các phiên thực tế.

Trong bối cảnh PAM, MFA coverage hỗ trợ ba quyết định:

- Ưu tiên xử lý tài khoản và đường truy cập có quyền cao nhưng chưa được bảo vệ.
- Xác định triển khai MFA đã chuyển từ cấu hình sang vận hành thực tế đến đâu.
- Cung cấp bằng chứng có thể truy nguyên khi rà soát quyền, kiểm toán hoặc điều tra sự cố.

Chỉ số này không thay thế least privilege, JIT/JEA, vault, luân chuyển credential hoặc giám sát phiên. Một tài khoản có MFA vẫn có thể giữ quá nhiều quyền; một credential đã được vault quản lý vẫn có thể bị dùng qua đường truy cập không buộc MFA. Các kiểm soát cần được đo riêng rồi đọc cùng nhau.

## 2. Những khái niệm phải phân biệt

MFA yêu cầu kết hợp các loại yếu tố xác thực độc lập, chẳng hạn yếu tố người dùng biết và yếu tố người dùng sở hữu. Nhập mật khẩu rồi nhập thêm một PIN thuộc cùng loại yếu tố kiến thức không tự tạo thành MFA. Mặt khác, số lần giao diện yêu cầu nhập liệu không đủ để kết luận mức bảo đảm của một phương thức xác thực; cần xem cơ chế và bằng chứng của chính phương thức đó.

| Khái niệm | Nội dung được đo | Điều chưa chứng minh được |
|---|---|---|
| MFA enrollment | Danh tính đã đăng ký phương thức đáp ứng chính sách | Đường truy cập đặc quyền bắt buộc sử dụng phương thức đó |
| Policy assignment | Danh tính hoặc nhóm đã được gán chính sách yêu cầu MFA | Chính sách thực sự áp dụng cho mọi đường, tài nguyên và ngữ cảnh cần bảo vệ |
| Verified enforcement | Có bằng chứng còn hiệu lực cho thấy yêu cầu MFA được thực thi | Mọi phiên trong quá khứ đều được bảo vệ hoặc không tồn tại danh tính chưa được kiểm kê |
| Observed session assurance | Các phiên hoặc lần cấp quyền thực tế có bằng chứng xác thực đạt yêu cầu | Những đường không được sử dụng hoặc không được thu thập log đã được bảo vệ |
| Phishing-resistant MFA coverage | Phần phạm vi được bảo vệ bằng phương thức đáp ứng yêu cầu chống phishing đã định nghĩa | Mọi phương thức được gọi là MFA đều có cùng mức bảo đảm |

Ví dụ, mật khẩu kết hợp mã OTP có thể đáp ứng một chính sách MFA, nhưng mã OTP có thể bị chuyển tiếp trong một cuộc tấn công phishing. Do đó, dashboard không nên đổi nhãn “có MFA” thành “chống phishing” khi chưa đánh giá thuộc tính của phương thức.

Ngược lại, không thấy một màn hình yêu cầu MFA mới ở mỗi ứng dụng cũng chưa chứng minh đường đó thiếu MFA. Một ứng dụng có thể nhận ngữ cảnh xác thực từ nhà cung cấp danh tính, gọi tắt là IdP. Cần kiểm tra mức bảo đảm được truyền, tính toàn vẹn của liên kết phiên, tuổi xác thực và cách ứng dụng hoặc PAM thực thi yêu cầu, thay vì đếm màn hình thử thách.

## 3. Xác định mẫu số trước khi tính tỷ lệ

### 3.1. Viết một hợp đồng đo lường rõ ràng

Một định nghĩa có thể sử dụng trong vận hành là:

> Tại thời điểm chốt số liệu, đo tỷ lệ tài khoản con người còn khả năng sử dụng quyền đặc biệt, bao gồm quyền thường trực và quyền đủ điều kiện kích hoạt theo JIT, mà mọi đường truy cập đặc quyền thuộc phạm vi đã được kiểm kê đều có bằng chứng thực thi MFA hợp lệ theo chính sách.

Định nghĩa này phải đi cùng phạm vi môi trường, loại tài nguyên, cách nhận diện tài khoản đặc quyền, tiêu chí bằng chứng còn hiệu lực và cách xử lý ngoại lệ. Đây là một lựa chọn đo lường minh họa, không phải định nghĩa duy nhất cho mọi tổ chức.

Nếu tổ chức chỉ đo quyền đang kích hoạt, phải đặt nhãn “active privileged access”. Nếu đo cả quyền đủ điều kiện kích hoạt, đặt nhãn thể hiện phần eligible. Không thay đổi qua lại giữa hai tập khi so sánh xu hướng.

### 3.2. Những đối tượng thường cần kiểm kê

Tùy phạm vi, tập đo có thể gồm tài khoản quản trị directory, hệ điều hành, cơ sở dữ liệu, thiết bị mạng, nền tảng đám mây, ứng dụng nhạy cảm và chính hệ thống PAM. Tài khoản quản trị của nhà cung cấp, tài khoản local, tài khoản liên kết và tài khoản khẩn cấp cũng cần được đánh giá nếu vẫn có thể thực hiện truy cập tương tác thuộc phạm vi.

Không chỉ lấy danh sách tài khoản đã onboard vào PAM làm mẫu số. Cách làm đó bỏ qua chính phần truy cập chưa được quản lý. Danh mục đặc quyền nên được đối soát từ các nguồn quản lý danh tính, quyền trên tài nguyên và kiểm kê hạ tầng trong phạm vi đã công bố.

Những cách xử lý cần thống nhất:

| Đối tượng | Cách xử lý trong chỉ số tài khoản con người |
|---|---|
| Quản trị viên có quyền thường trực | Đưa vào nếu tài khoản còn khả năng truy cập thuộc phạm vi |
| Người có quyền eligible theo JIT | Đưa vào nếu hợp đồng đo bao gồm cơ hội kích hoạt; kiểm tra cả bước kích hoạt và đường sử dụng quyền |
| Tài khoản ít dùng nhưng vẫn enabled | Không loại chỉ vì không có lần đăng nhập gần đây |
| Tài khoản vendor còn quyền | Đưa vào theo đúng phạm vi; không coi nhà cung cấp là lý do miễn đo |
| Tài khoản break-glass | Giữ khả năng quan sát riêng; ngoại lệ được duyệt không tự biến thành đã có MFA |
| Tài khoản đã vô hiệu hóa | Chỉ loại khi đã xác minh không còn khả năng truy cập liên quan, kể cả phiên hoặc credential còn hiệu lực |
| Service account hoặc workload identity | Phân loại riêng nếu thực sự chỉ dùng theo cơ chế máy với máy; không mặc định coi là MFA-covered |
| Tài khoản gắn nhãn service nhưng vẫn cho người đăng nhập tương tác | Đánh giá đường tương tác đó; không loại chỉ dựa vào tên hoặc nhãn |

Với tài khoản máy, các kiểm soát thích hợp có thể là workload identity, credential ngắn hạn, ràng buộc nguồn sử dụng, vault và luân chuyển secret. Những kiểm soát đó cần chỉ số riêng. Gộp toàn bộ tài khoản máy vào mẫu số MFA của người dùng có thể làm tỷ lệ khó diễn giải; đánh dấu chúng đều đạt MFA lại tạo kết quả sai.

### 3.3. Chọn đơn vị đếm và tránh đếm trùng

Một người có thể có tài khoản làm việc thông thường, tài khoản quản trị directory và tài khoản quản trị đám mây. Nếu đo theo tài khoản, ba đối tượng đó không được gộp chỉ vì cùng địa chỉ email. Nếu đo theo người, chỉ kết luận người đó được bao phủ khi các tài khoản và quyền đặc biệt liên quan đều đạt điều kiện của định nghĩa.

Danh tính nên có khóa ổn định gắn với nguồn định danh và đối tượng tài khoản, chẳng hạn `source_system + principal_id`. Không dùng display name làm khóa duy nhất. Tài khoản đồng bộ hoặc liên kết cần quy tắc ánh xạ để không đếm hai lần cùng một đối tượng, nhưng cũng không được gộp hai tài khoản khác nhau ngoài ý muốn.

## 4. Đo theo đường truy cập để phát hiện khoảng trống

Một tài khoản có thể truy cập cùng tài nguyên qua nhiều đường. Đơn vị đường truy cập có thể được mô hình hóa thành:

```text
Tài khoản + tài nguyên/nhóm tài nguyên + quyền + đường truy cập + điều kiện áp dụng
```

Ví dụ: tài khoản `admin-demo` có thể dùng cổng PAM để mở phiên tới máy chủ và cũng có thể dùng một đường quản trị trực tiếp. Hai đường phải được đánh giá riêng.

| Đường truy cập minh họa | Câu hỏi cần xác minh | Kết quả có thể gặp |
|---|---|---|
| IdP → PAM → phiên quản trị | MFA có bị bắt buộc, đúng danh tính và đúng mức bảo đảm trước khi cấp phiên không? | Có thể được bao phủ nếu chuỗi bằng chứng đầy đủ |
| IdP → console đám mây | Chính sách có áp dụng đúng role, ứng dụng và điều kiện đăng nhập không? | Có thể khác với chính sách áp dụng cho PAM |
| Đăng nhập local trực tiếp | Đường này có bị chặn hoặc có kiểm soát MFA tương đương đã được xác minh không? | Có thể là lỗ hổng dù cổng PAM đã đạt |
| Khôi phục hoặc reset phương thức MFA | Quy trình có cho phép nhận lại quyền quản trị mà bỏ qua mức bảo đảm yêu cầu không? | Có thể tạo đường đi vòng |
| Credential checkout từ vault | Việc nhận credential và khả năng sử dụng credential ngoài phiên được kiểm soát có được đánh giá không? | MFA tại thời điểm checkout chưa đủ chứng minh mọi lần sử dụng sau đó |
| Kích hoạt JIT rồi dùng quyền | Bằng chứng MFA tại kích hoạt có còn hợp lệ cho cách sử dụng quyền theo chính sách không? | Có thể cần ràng buộc phiên, thời gian hoặc xác thực lại |

Một đường direct access đã được chặn bằng kiểm soát có hiệu lực có thể không còn là đường khả dụng. Việc loại đường đó phải có bằng chứng chặn và thời điểm hiệu lực, không chỉ dựa vào tài liệu thiết kế. Nếu không chắc đường còn khả dụng hay không, giữ trạng thái chưa xác định và tạo việc đối soát.

Để đánh giá bao phủ đầu cuối, cần xác minh rằng người dùng không thể đi tới quyền đặc biệt bằng một đường khác không thỏa yêu cầu MFA. Không nhất thiết mọi hệ thống đều phải tự phát ra thử thách MFA; yêu cầu là chuỗi truy cập được ràng buộc vào ngữ cảnh xác thực hợp lệ và không có đường bỏ qua trong phạm vi đã kiểm kê.

## 5. Công thức chính và quy tắc trạng thái

### 5.1. Ba trạng thái cho từng đối tượng

Tại thời điểm `t`, gọi `S(t)` là tập tài khoản thuộc phạm vi. Với mỗi tài khoản, phân loại:

- `COVERED`: danh mục đường truy cập đã được xác nhận đầy đủ trong phạm vi, có ít nhất một đường khả dụng, và mọi đường đều có bằng chứng thực thi MFA hợp lệ.
- `GAP`: đã biết ít nhất một đường khả dụng không đáp ứng yêu cầu MFA, kể cả đường có ngoại lệ được duyệt.
- `UNKNOWN`: chưa thấy lỗ hổng đã xác nhận nhưng thiếu dữ liệu để kết luận bao phủ, chẳng hạn thiếu danh mục đường, bằng chứng quá hạn hoặc nguồn dữ liệu ngừng cập nhật.

Nếu một tài khoản vừa có một đường đã xác nhận thiếu MFA vừa có một đường chưa rõ, trạng thái tổng hợp là `GAP`; đồng thời vẫn giữ thông tin thiếu dữ liệu ở cấp đường. Không để `UNKNOWN` che khuất một lỗ hổng đã biết.

Gọi `C`, `G`, `U` lần lượt là số tài khoản thuộc ba trạng thái. Khi phân loại đầy đủ:

```text
N = |S(t)| = C + G + U

Verified MFA coverage (%) = 100 × C / N
Known gap rate (%)       = 100 × G / N
Unknown rate (%)         = 100 × U / N
```

`UNKNOWN` vẫn ở mẫu số nhưng không vào tử số đã được xác minh. Đây là cách công bố thận trọng về mức có bằng chứng, không có nghĩa đã chứng minh mọi đối tượng unknown đều thiếu MFA.

Nếu `N = 0`, trả về `N/A` hoặc giá trị rỗng kèm số lượng bằng 0. Không tự trả 100%. Nếu cả nguồn kiểm kê bị mất, cũng không được dùng một tập rỗng do lỗi thu thập để kết luận không còn tài khoản đặc quyền.

### 5.2. Các tỷ lệ bổ sung cần đặt tên riêng

```text
Enrollment coverage = số tài khoản đã đăng ký phương thức phù hợp / N

Configured coverage = số tài khoản được cấu hình chính sách yêu cầu MFA / N

Verified route coverage = số đường đã xác minh đạt / tổng đường khả dụng đã biết

Observed assurance rate = số đơn vị hoạt động có bằng chứng đạt /
                          tổng đơn vị hoạt động thuộc phạm vi trong kỳ
```

Các công thức trên nhân 100 khi hiển thị theo phần trăm. Mỗi chỉ số có thể cần điều kiện dữ liệu bổ sung. Tỷ lệ theo đường chỉ phản ánh danh mục đường đã biết; phải công bố riêng mức đầy đủ của danh mục. Tỷ lệ theo hoạt động phải chỉ rõ đơn vị là phiên, lần kích hoạt hay lần cấp quyền, đồng thời giữ các bản ghi thiếu bằng chứng trong nhóm unknown.

Không lấy trung bình đơn giản tỷ lệ của các nhóm có quy mô khác nhau. Tỷ lệ toàn phạm vi phải tính từ tổng tử số chia tổng mẫu số. Tỷ lệ có trọng số rủi ro, nếu dùng, là một chỉ số khác và phải công bố trọng số.

### 5.3. Mức bảo đảm là một chiều đo độc lập

Một hệ thống có thể đã bắt buộc MFA nhưng chưa đáp ứng yêu cầu chống phishing cho tài khoản nhạy cảm nhất. Khi đó nên công bố đồng thời tỷ lệ verified MFA và tỷ lệ đáp ứng mức bảo đảm yêu cầu, chẳng hạn phishing-resistant coverage của một cohort cụ thể.

Nếu yêu cầu chính thức của cohort đã là MFA chống phishing, các đường chỉ đáp ứng MFA thông thường không được tính đạt trong chỉ số tuân theo yêu cầu đó. Định nghĩa tử số phải phản ánh chính sách đang đo, thay vì thay nhãn trên cùng một tập số liệu.

## 6. Ví dụ tính đầy đủ từ dữ liệu kiểm kê

Một tổ chức minh họa kiểm kê được 134 tài khoản liên quan đến quyền đặc biệt:

- 100 tài khoản con người còn khả năng truy cập tương tác thuộc phạm vi, bao gồm tài khoản eligible theo JIT và tài khoản khẩn cấp.
- 30 danh tính máy đã được xác minh chỉ dùng theo cơ chế máy với máy, được theo dõi bằng chỉ số riêng.
- 4 tài khoản đã bị vô hiệu hóa và đã xác minh không còn khả năng sử dụng quyền trong phạm vi chốt số liệu.

Mẫu số của chỉ số tài khoản con người là 100. Đây là kết quả phân loại có bằng chứng, không phải lấy 134 trừ tùy ý các nhóm khó triển khai MFA.

Trong 100 tài khoản này, 92 đã đăng ký phương thức MFA phù hợp và 88 được cấu hình chính sách yêu cầu MFA. Sau khi đối chiếu mọi đường truy cập và bằng chứng thực thi, kết quả là:

| Nhóm rủi ro | Tổng tài khoản | COVERED | GAP | UNKNOWN | Verified coverage |
|---|---:|---:|---:|---:|---:|
| Quản trị trọng yếu | 20 | 17 | 2 | 1 | 85% |
| Quản trị vận hành | 50 | 42 | 5 | 3 | 84% |
| Hỗ trợ và vendor | 30 | 21 | 5 | 4 | 70% |
| Toàn phạm vi | 100 | 80 | 12 | 8 | 80% |

Các tỷ lệ cần được đọc đúng:

```text
Enrollment coverage     = 92 / 100 = 92%
Configured coverage     = 88 / 100 = 88%
Verified MFA coverage   = 80 / 100 = 80%
Known gap rate          = 12 / 100 = 12%
Unknown rate            =  8 / 100 =  8%
```

Trung bình không trọng số của ba tỷ lệ nhóm là khoảng 79,67%, khác với tỷ lệ toàn phạm vi 80%. Cách tổng hợp đúng ở đây là `(17 + 42 + 21) / (20 + 50 + 30)`.

Giả sử 3 trong 12 tài khoản `GAP` có ngoại lệ còn hiệu lực. Chúng vẫn nằm trong nhóm chưa đáp ứng MFA của chỉ số chính. Có thể trình bày thêm “3 gap có chấp thuận tạm thời, 9 gap chưa có chấp thuận còn hiệu lực”, nhưng không tăng tử số lên 83. Chấp thuận rủi ro thay đổi cách xử lý, không thay đổi sự thật kỹ thuật rằng đường truy cập chưa đáp ứng MFA.

Giả sử thêm 65 tài khoản trong tập này có bằng chứng mọi đường đáp ứng yêu cầu MFA chống phishing. Tỷ lệ tương ứng là 65/100 = 65%. Nó không mâu thuẫn với 80% bao phủ MFA thông thường, vì hai tử số kiểm tra hai mức bảo đảm khác nhau.

Từ dữ liệu trên, hành động ưu tiên không đơn thuần là nhắc 8 tài khoản chưa đăng ký MFA. Hai gap thuộc nhóm quản trị trọng yếu và một tài khoản trọng yếu unknown cần được phân tích theo quyền, khả năng khai thác và thời gian tồn tại. Khoảng cách giữa 92% đăng ký và 80% thực thi cho thấy phần việc còn nằm ở chính sách, đường truy cập và bằng chứng, không chỉ ở enrollment.

## 7. Bằng chứng nào đủ để đưa vào tử số?

### 7.1. Ghép cấu hình với hành vi thực tế

Một hồ sơ bao phủ nên có bằng chứng từ nhiều mặt:

1. Tài khoản và quyền thuộc phạm vi được nhận diện từ nguồn có trách nhiệm.
2. Chính sách hiệu lực yêu cầu đúng mức MFA cho tài khoản, ứng dụng, tài nguyên và ngữ cảnh.
3. Luồng truy cập hợp lệ thể hiện mức bảo đảm đã được đáp ứng và gắn với đúng phiên hoặc lần cấp quyền.
4. Kiểm tra phủ định theo kế hoạch xác nhận không thể nhận quyền đặc biệt khi thiếu điều kiện MFA cần thiết.
5. Các đường dự phòng, khôi phục, direct access và ngoại lệ được đối soát.

Kiểm tra phủ định là kiểm tra rằng hệ thống từ chối khi điều kiện bảo vệ không đạt, không phải tìm cách vượt kiểm soát ngoài phạm vi. Trong thực hành, dùng tài khoản thử nghiệm, cửa sổ thử nghiệm và quyền đã được phê duyệt; tránh gây khóa tài khoản hoặc tác động tới truy cập khẩn cấp đang cần cho vận hành.

Một ảnh chụp màn hình “MFA enabled” không đủ để chứng minh mọi đường truy cập đã được bảo vệ. Một dòng log thành công cũng không đủ nếu không biết chính sách nào áp dụng, danh tính nào được liên kết và có đường thay thế nào chưa kiểm tra.

### 7.2. Ngữ cảnh xác thực từ IdP phải được đánh giá đúng

Trong liên kết danh tính, PAM có thể dựa vào thông tin mức xác thực từ IdP. Cần xác minh ứng dụng kiểm tra thông tin đó đúng cách và không chỉ tin một nhãn do phía không đáng tin cậy cung cấp. Nội dung cần đánh giá bao gồm:

- Ngữ cảnh xác thực có tương ứng với phương thức và mức bảo đảm mà chính sách chấp nhận không.
- Ngữ cảnh đó có gắn với đúng tài khoản, ứng dụng nhận và phiên được cấp quyền không.
- Tuổi xác thực có còn phù hợp khi mở phiên đặc quyền hoặc kích hoạt quyền không.
- Có điều kiện nào khiến chính sách bỏ qua MFA, như nhóm loại trừ, đường legacy hoặc chế độ fallback không.
- Phiên đã có từ trước thay đổi chính sách được xử lý thế nào.

Không quy ước rằng mọi lần đăng nhập đều phải phát sinh thử thách MFA mới. Nếu chính sách cho phép dùng lại một phiên có mức bảo đảm còn hợp lệ, hoạt động đó có thể đạt yêu cầu. Ngược lại, token hoặc cookie được chấp nhận không tự chứng minh phiên còn đáp ứng giới hạn thời gian, danh tính và mức xác thực yêu cầu.

### 7.3. Bằng chứng có tuổi và có phiên bản

Hồ sơ cần lưu `observed_at`, `collected_at`, nguồn, phiên bản chính sách hoặc cấu hình liên quan, kết quả đánh giá và tham chiếu bằng chứng. Không chỉ lưu một cờ `mfa=true` không có nguồn gốc.

Tuổi bằng chứng phải dựa trên chính sách nội bộ và tốc độ thay đổi của hệ thống. Ví dụ minh họa: một tổ chức yêu cầu cấu hình được thu thập trong 24 giờ và kiểm tra luồng truy cập trong 30 ngày. Hai giá trị này chỉ là lựa chọn cho bài thực hành; không phải ngưỡng mặc định áp dụng cho mọi môi trường.

Một kiểm tra luồng còn trong hạn 30 ngày vẫn có thể mất hiệu lực sớm nếu chính sách, đường truy cập hoặc cơ chế liên kết danh tính vừa thay đổi. Khi thay đổi làm mất cơ sở kết luận cũ, trạng thái chuyển sang `UNKNOWN` cho tới khi có bằng chứng thay thế. Nếu thay đổi đã xác nhận mở đường không có MFA, trạng thái là `GAP`.

Nếu nguồn log ngừng gửi, không tự giữ số xanh vô thời hạn và cũng không giả định kiểm soát chắc chắn đã tắt. Công bố trạng thái thiếu bằng chứng, độ trễ thu thập và thời điểm cuối nguồn còn hoạt động.

## 8. Mô hình dữ liệu cho chỉ số có thể truy nguyên

Không cần gom toàn bộ log thô vào một bảng dashboard. Có thể chuẩn hóa thành các tập dữ liệu nhỏ, nhưng mỗi kết luận phải truy về bằng chứng được kiểm soát truy cập.

| Tập dữ liệu | Các trường minh họa | Mục đích |
|---|---|---|
| Tài khoản trong snapshot | `snapshot_id`, `principal_key`, loại danh tính, trạng thái, `risk_tier`, owner | Chốt mẫu số và đơn vị đếm |
| Quyền đặc biệt | tài khoản, tài nguyên, quyền, standing/eligible/active, thời điểm hiệu lực | Giải thích tại sao tài khoản thuộc phạm vi |
| Danh mục đường | tài khoản, `route_key`, loại đường, tài nguyên, khả dụng, trạng thái đầy đủ | Phát hiện và quản lý đường truy cập |
| Đánh giá đường | snapshot, `route_key`, `COVERED/GAP/UNKNOWN`, lý do, thời điểm đánh giá | Tổng hợp trạng thái có quy tắc |
| Bằng chứng | mã tham chiếu, nguồn, thời điểm quan sát/thu thập, phiên bản chính sách, hạn hiệu lực | Xác minh cơ sở của kết luận |
| Ngoại lệ | phạm vi, lý do, người chịu trách nhiệm, người phê duyệt, hết hạn, kiểm soát bù | Theo dõi chấp thuận và xử lý gap |

`route_key` phải phân biệt được các đường có điều kiện bảo vệ khác nhau. Không gộp đường qua PAM và đường direct access thành một dòng chỉ vì cùng tới một máy chủ. Nếu tổng hợp theo nhóm tài nguyên, phải có cơ sở chứng minh các tài nguyên trong nhóm thực sự chịu cùng cấu hình và điều kiện; cần phát hiện thành viên lệch cấu hình.

Mỗi snapshot nên có một bản ghi cho mỗi tài khoản theo khóa đã chọn, và một kết quả đã chuẩn hóa cho mỗi đường trong snapshot. Dữ liệu trùng, xung đột, thiếu nguồn hoặc sai thời gian cần được đánh dấu trước khi tổng hợp. Không chọn tùy tiện bản ghi “đẹp nhất” để tăng tử số.

Một bản ghi đánh giá minh họa:

```json
{
  "snapshot_id": "demo-snapshot-01",
  "principal_key": "directory-demo:admin-017",
  "route_key": "admin-017:server-group-a:direct-admin",
  "required_assurance": "mfa",
  "state": "GAP",
  "reason": "DIRECT_ROUTE_DOES_NOT_ENFORCE_REQUIRED_MFA",
  "policy_revision": "demo-policy-4",
  "evidence_ref": "evidence-demo-204",
  "exception_ref": "exception-demo-08"
}
```

Mã ngoại lệ không làm `state` chuyển sang `COVERED`. Nó bổ sung ngữ cảnh xử lý cho gap đã biết. Dữ liệu minh họa không chứa secret, token phiên, mã khôi phục hoặc nội dung credential.

## 9. Ví dụ tổng hợp bằng SQL

Ví dụ sau mô tả lớp tổng hợp sau khi đánh giá bằng chứng. Đây không phải truy vấn đọc trực tiếp log của một sản phẩm PAM hay IdP cụ thể.

Giả định có hai bảng:

- `privileged_subject_snapshot`: một dòng mỗi tài khoản mỗi snapshot; `in_scope` đã được xác định theo hợp đồng đo, `inventory_complete` xác nhận danh mục đường truy cập đủ trong phạm vi.
- `privileged_route_snapshot`: một dòng mỗi đường khả dụng mỗi tài khoản mỗi snapshot; `route_state` đã được đánh giá thành `COVERED`, `GAP` hoặc `UNKNOWN` theo bằng chứng và mức bảo đảm yêu cầu.

Các đường đã chặn và được xác minh không còn khả dụng được quản lý trong danh mục gốc nhưng không nằm trong bảng đường khả dụng của ví dụ. Tham số `:snapshot_id` chọn một snapshot duy nhất. Cú pháp tham số cần được điều chỉnh theo công cụ truy vấn thực tế.

```sql
WITH subject_state AS (
    SELECT
        s.snapshot_id,
        s.principal_key,
        s.risk_tier,
        CASE
            WHEN SUM(CASE WHEN r.route_state = 'GAP'
                          THEN 1 ELSE 0 END) > 0
                THEN 'GAP'
            WHEN s.inventory_complete IS NOT TRUE
                THEN 'UNKNOWN'
            WHEN COUNT(r.route_key) = 0
                THEN 'UNKNOWN'
            WHEN SUM(CASE WHEN r.route_state = 'COVERED'
                          THEN 1 ELSE 0 END) = COUNT(r.route_key)
                THEN 'COVERED'
            ELSE 'UNKNOWN'
        END AS state
    FROM privileged_subject_snapshot s
    LEFT JOIN privileged_route_snapshot r
      ON r.snapshot_id = s.snapshot_id
     AND r.principal_key = s.principal_key
    WHERE s.snapshot_id = :snapshot_id
      AND s.in_scope = TRUE
    GROUP BY
        s.snapshot_id,
        s.principal_key,
        s.risk_tier,
        s.inventory_complete
)
SELECT
    COUNT(*) AS total_subjects,
    COALESCE(SUM(CASE WHEN state = 'COVERED'
                      THEN 1 ELSE 0 END), 0) AS covered_subjects,
    COALESCE(SUM(CASE WHEN state = 'GAP'
                      THEN 1 ELSE 0 END), 0) AS gap_subjects,
    COALESCE(SUM(CASE WHEN state = 'UNKNOWN'
                      THEN 1 ELSE 0 END), 0) AS unknown_subjects,
    100.0 * COALESCE(SUM(CASE WHEN state = 'COVERED'
                              THEN 1 ELSE 0 END), 0)
          / NULLIF(COUNT(*), 0) AS verified_coverage_pct
FROM subject_state;
```

Những điểm quan trọng của truy vấn:

- Bắt đầu từ tập tài khoản thuộc phạm vi và dùng `LEFT JOIN`, nên tài khoản chưa có dữ liệu đường truy cập không biến mất khỏi mẫu số.
- Một đường `GAP` đủ để kết luận tài khoản có gap, ngay cả khi danh mục đường chưa đầy đủ.
- Không có đường khả dụng trong dữ liệu nhưng vẫn có tài khoản in-scope được đưa về `UNKNOWN`, cần đối soát thay vì tự coi đạt.
- Chỉ đạt khi danh mục đã được xác nhận đầy đủ và tất cả các đường hiện có đều đạt.
- Không lọc ngoại lệ hoặc tài khoản không có log ra khỏi mẫu số.
- `NULLIF` giữ kết quả tỷ lệ là rỗng khi mẫu số bằng 0; `100.0` tránh ý định chia số nguyên trong phép tính tỷ lệ.

Truy vấn này phụ thuộc vào độ đúng của lớp chuẩn hóa. Nó không tự phát hiện tài khoản chưa có trong kiểm kê, đường bị bỏ sót hoặc kết quả đánh giá bằng chứng sai. Ràng buộc duy nhất theo khóa, đối soát nguồn và kiểm tra độ đầy đủ của snapshot là phần bắt buộc của hệ thống tính chỉ số.

Khi cần chia theo nhóm rủi ro, tổng hợp `subject_state` theo `risk_tier`. Tính tỷ lệ toàn phạm vi trực tiếp từ toàn bộ dòng tài khoản, không lấy trung bình các phần trăm đã làm tròn trên biểu đồ nhóm.

## 10. Tách bao phủ cấu trúc khỏi hoạt động trong kỳ

Verified MFA coverage tại một thời điểm cho biết trạng thái bảo vệ đã được xác minh của tập tài khoản. Một tỷ lệ theo hoạt động trả lời câu hỏi khác: trong các phiên hoặc lần cấp quyền thuộc kỳ, bao nhiêu đơn vị có bằng chứng mức xác thực đạt yêu cầu?

Ví dụ minh họa trong một kỳ có 1.000 lần cấp quyền đặc biệt đã được nhận diện:

```text
Có bằng chứng đạt mức xác thực yêu cầu: 930
Có bằng chứng không đạt:                 20
Thiếu bằng chứng để kết luận:            50

Observed assurance rate = 930 / 1.000 = 93%
```

Kết quả 93% không thay thế verified account coverage 80% của ví dụ trước. Một nhóm nhỏ có thể tạo ra phần lớn hoạt động hợp lệ, trong khi các tài khoản còn lại hiếm khi đăng nhập và vẫn có đường không được bảo vệ.

Để tỷ lệ theo hoạt động có nghĩa, cần định nghĩa:

- Đếm một lần cấp quyền, một phiên hay một yêu cầu truy cập; không trộn các đơn vị.
- Dùng khóa nào để nối sự kiện xác thực, kích hoạt JIT và phiên quản trị.
- Xử lý phiên kéo dài qua ranh giới kỳ và sự kiện đến trễ ra sao.
- Trường hợp dùng lại ngữ cảnh xác thực nào được chính sách chấp nhận.
- Những nguồn nào cung cấp tổng hoạt động, tránh lấy riêng log MFA làm mẫu số.

Đếm “số sự kiện MFA thành công / số sự kiện MFA” là tỷ lệ thành công của một luồng xác thực, không phải tỷ lệ bao phủ toàn bộ hoạt động đặc quyền. Những hoạt động không hề đi qua luồng MFA có thể vắng hoàn toàn khỏi tập dữ liệu đó.

## 11. Ngoại lệ, break-glass và kiểm soát bù

Một số hệ thống cần truy cập khẩn cấp khi các thành phần xác thực thông thường không hoạt động. Thiết kế tài khoản break-glass phải cân bằng khả năng khôi phục và kiểm soát rủi ro, nhưng dashboard vẫn cần phản ánh đúng thuộc tính kỹ thuật của đường khẩn cấp.

Với một đường khẩn cấp không đáp ứng yêu cầu MFA đang đo:

- Ghi nhận gap và phân biệt rõ ngoại lệ còn hiệu lực hay đã hết hạn.
- Lưu owner, phạm vi, lý do tồn tại, phê duyệt và thời điểm rà soát.
- Theo dõi kiểm soát bù phù hợp như hạn chế nơi sử dụng, kiểm soát lấy credential, cảnh báo tức thời và rà soát sau sử dụng.
- Đánh giá việc thu hồi hoặc luân chuyển credential, đóng phiên và khôi phục trạng thái bảo vệ sau sự kiện.

Các kiểm soát bù giúp quản lý rủi ro, nhưng không tự trở thành yếu tố MFA. Quy trình hai người phê duyệt, camera tại phòng máy hoặc cảnh báo phiên không tự chứng minh đường đăng nhập đáp ứng xác thực đa yếu tố.

Nếu muốn có chỉ số “đáp ứng chính sách hoặc có ngoại lệ được chấp thuận”, phải đặt tên riêng và trình bày cạnh tỷ lệ MFA thực tế. Không dùng một con số đã điều chỉnh ngoại lệ để đại diện cho MFA coverage mà không giải thích.

Ngoại lệ hết hạn không tự làm quyền truy cập biến mất. Cần cơ chế xử lý cụ thể: gia hạn có phê duyệt và đánh giá lại, khắc phục kiểm soát hoặc loại bỏ khả năng truy cập theo quy trình. Dashboard phải thể hiện tuổi gap, tuổi ngoại lệ và trách nhiệm xử lý để tránh tồn đọng không thời hạn.

## 12. Dashboard phục vụ quyết định vận hành

Một bảng điều khiển hữu ích nên đưa tỷ lệ chính đi cùng số tuyệt đối và chất lượng dữ liệu. Với ví dụ 100 tài khoản, dòng tổng quan có thể là:

```text
Verified MFA coverage: 80% (80/100 tài khoản)
Known gaps: 12 tài khoản, trong đó 3 có ngoại lệ còn hiệu lực
Unknown: 8 tài khoản
Quản trị trọng yếu: 85% (17/20), 2 gap, 1 unknown
Mức bảo đảm chống phishing đã xác minh: 65% (65/100)
Snapshot và độ mới dữ liệu: hiển thị theo từng nguồn
```

Các chiều phân tích nên ưu tiên những gì có thể giao việc: owner, nhóm rủi ro, môi trường, loại tài nguyên, standing/eligible, loại đường, vendor/nội bộ và lý do gap. Một tài khoản có nhiều đường lỗi cần cho phép xem chi tiết mà vẫn chỉ được đếm một lần trong tỷ lệ tài khoản.

Danh sách hành động cần chứa tài khoản hoặc đường liên quan, quyền có thể nhận, mức ảnh hưởng, owner, loại thiếu sót, bằng chứng, thời điểm phát hiện và hạn xử lý nội bộ. Không đưa secret, token hay mã khôi phục lên dashboard hoặc nhãn metric.

Với hệ thống metric theo chuỗi thời gian, dùng nhãn có số lượng giá trị được kiểm soát như risk tier hoặc loại đường cho số liệu tổng hợp. Danh sách từng tài khoản và bằng chứng chi tiết nên nằm trong kho có phân quyền. Đưa ID tài khoản hoặc mã sự kiện thay đổi liên tục vào mọi nhãn vừa tăng chi phí lưu trữ vừa mở rộng phạm vi lộ dữ liệu.

### 12.1. Phân biệt biến động kiểm soát và biến động mẫu số

Ngày đầu có 80 tài khoản đạt trên 100 tài khoản: tỷ lệ 80%. Ngày sau phát hiện thêm 20 tài khoản đặc quyền chưa được xác minh, nên tỷ lệ trở thành 80/120, khoảng 66,67%.

Tỷ lệ giảm không nhất thiết do 20 tài khoản cũ mất MFA. Nó có thể phản ánh danh mục được kiểm kê đầy đủ hơn. Báo cáo nên tách số mới phát hiện, số mới đạt, số mất bao phủ, số chuyển unknown và số thực sự rời phạm vi.

Nếu một tài khoản rời mẫu số do đã bị loại bỏ quyền và không còn khả năng truy cập, đó là thay đổi có thể làm giảm rủi ro. Nếu nó rời mẫu số chỉ do thay bộ lọc báo cáo, cần công bố thay đổi định nghĩa và không so sánh trực tiếp chuỗi trước/sau như thể cùng một chỉ số.

### 12.2. Mục tiêu và cảnh báo phải gắn với cohort

Mục tiêu có thể khác nhau giữa quản trị trọng yếu và hệ thống đang chuyển đổi. Các ngưỡng cụ thể cần được phê duyệt theo yêu cầu của tổ chức; không có một tỷ lệ trung bình tự động chứng minh toàn bộ truy cập đã an toàn.

Ngoài cảnh báo tụt tỷ lệ, nên cân nhắc các tín hiệu có hành động rõ ràng: xuất hiện một đường không có MFA ở nhóm trọng yếu, có ngoại lệ hết hạn, bằng chứng thực thi quá hạn, nguồn kiểm kê ngừng cập nhật hoặc có tài khoản đặc quyền mới chưa được đánh giá.

Tỷ lệ đạt 100% trong phạm vi đã đo vẫn cần được đọc cùng độ đầy đủ kiểm kê, mức bảo đảm yêu cầu và tính còn hiệu lực của bằng chứng. Không dùng con số đó để kết luận không còn rủi ro chiếm phiên, lạm dụng quyền hoặc lộ credential.

## 13. Những cách đo dễ tạo kết luận sai

| Cách đo hoặc cách trình bày | Vì sao gây sai lệch | Cách làm rõ |
|---|---|---|
| Đã đăng ký MFA thì tính covered | Đăng ký không buộc mọi đường sử dụng MFA | Công bố enrollment riêng và đo thực thi |
| Chỉ lấy tài khoản đã vào PAM | Bỏ phần quản trị chưa được quản lý | Đối soát tập đặc quyền từ các nguồn trong phạm vi |
| Có một đường đạt thì tài khoản đạt | Bỏ qua đường dự phòng hoặc direct access | Tổng hợp theo điều kiện mọi đường cần bảo vệ đều đạt |
| Không có log thì loại khỏi mẫu số | Làm biến mất tài khoản ít dùng hoặc nguồn bị lỗi | Giữ đối tượng in-scope và đánh dấu unknown |
| Ngoại lệ được duyệt tính như MFA | Trộn chấp thuận rủi ro với hiệu lực kiểm soát | Giữ gap kỹ thuật, thêm nhãn ngoại lệ |
| Mọi service account đều là N/A | Có thể còn đường đăng nhập tương tác | Xác minh loại sử dụng và đo đường tương tác nếu có |
| Giữ kết quả kiểm tra cũ vô thời hạn | Chính sách và đường truy cập có thể đã đổi | Gắn hạn và điều kiện mất hiệu lực của bằng chứng |
| Dùng số lần MFA thành công làm mẫu số hoạt động | Những lần không qua MFA không xuất hiện | Xây tập hoạt động độc lập rồi ghép bằng chứng xác thực |
| Lấy trung bình tỷ lệ nhóm | Nhóm nhỏ và lớn bị cho cùng trọng số | Tổng hợp từ tử số và mẫu số gốc |
| Gọi mọi MFA là chống phishing | Mức bảo đảm giữa phương thức khác nhau | Định nghĩa và đo riêng thuộc tính yêu cầu |
| Mẫu số 0 hiển thị 100% | Che lỗi kiểm kê hoặc phạm vi không có dữ liệu | Hiển thị N/A, số lượng và tình trạng nguồn |

Một lỗi khác là chỉ theo dõi phần trăm mà không theo dõi số gap tuyệt đối. Tỷ lệ có thể tăng vì thêm nhiều tài khoản đã được bảo vệ, trong khi một đường quản trị cực kỳ nhạy cảm không có MFA vẫn tồn tại. Việc ưu tiên xử lý cần đọc cả quyền thực tế và khả năng truy cập, không chỉ mức đóng góp vào tỷ lệ chung.

## 14. Bài thực hành: từ số liệu đến việc cần xử lý

Sử dụng dữ liệu giả lập hoặc môi trường thử nghiệm đã được phép. Mục tiêu là tạo một báo cáo có thể giải thích từng tài khoản trong mẫu số và từng đối tượng trong tử số, không cần vận hành một sản phẩm cụ thể.

### Bước 1: Chốt hợp đồng đo

Ghi rõ thời điểm snapshot, môi trường, loại tài khoản, cách xử lý standing và eligible, mức MFA yêu cầu, đơn vị đếm, quy tắc ngoại lệ và bằng chứng hết hiệu lực. Chọn tài khoản làm đơn vị để áp dụng công thức trong bài.

### Bước 2: Chuẩn bị tập kiểm kê và đường truy cập

Tạo dữ liệu minh họa cho 10 tài khoản con người có quyền đặc biệt:

- 6 tài khoản có danh mục đầy đủ và mọi đường đã xác minh đạt.
- 1 tài khoản có đường qua PAM đạt nhưng đường direct access đã xác nhận thiếu MFA.
- 1 tài khoản khẩn cấp có đường không đáp ứng MFA và ngoại lệ còn hiệu lực.
- 1 tài khoản chỉ có bằng chứng kiểm tra đã quá hạn.
- 1 tài khoản mới được phát hiện, chưa có danh mục đường đầy đủ.

Hai tài khoản cuối chưa có gap đã xác nhận nên được phân loại unknown. Tài khoản khẩn cấp vẫn là gap theo định nghĩa kỹ thuật, dù việc tồn tại của nó được chấp thuận tạm thời.

### Bước 3: Tính kết quả và giải thích

```text
N = 10
C = 6
G = 2
U = 2

Verified MFA coverage = 60%
Known gap rate        = 20%
Unknown rate          = 20%
```

Nếu loại hai unknown và tài khoản khẩn cấp ra khỏi mẫu số, kết quả sẽ thành 6/7, khoảng 85,71%. Con số đó không còn là chỉ số đã định nghĩa cho toàn bộ 10 tài khoản và che khuất ba đối tượng cần được quản lý.

### Bước 4: Giao hành động theo nguyên nhân

Với đường direct access, xác định cách buộc kiểm soát tương đương hoặc chặn đường theo quy trình thay đổi, rồi xác minh lại. Với tài khoản khẩn cấp, kiểm tra thời hạn ngoại lệ và bằng chứng kiểm soát bù. Với bằng chứng quá hạn, thu thập hoặc kiểm tra lại đúng đường. Với tài khoản mới, hoàn thành kiểm kê quyền và đường truy cập trước khi kết luận bao phủ.

Không đóng việc chỉ bằng ảnh chụp đã gán chính sách. Điều kiện chuyển sang `COVERED` là đáp ứng toàn bộ quy tắc về danh mục đường và bằng chứng trong hợp đồng đo.

### Bước 5: Mô phỏng thay đổi và đọc xu hướng

Giả sử tài khoản có direct access được khắc phục, các đường đều đã xác minh đạt, và tài khoản có bằng chứng quá hạn được kiểm tra lại thành công. Khi các điều kiện khác giữ nguyên:

```text
C = 8, G = 1, U = 1, N = 10
Verified MFA coverage = 80%
```

Nếu sau đó phát hiện thêm một tài khoản đặc quyền chưa đủ dữ liệu, mẫu số thành 11 và tỷ lệ là 8/11, khoảng 72,73%. Báo cáo cần giải thích đây là mở rộng kiểm kê, không diễn giải rằng hai biện pháp vừa khắc phục đã mất tác dụng.

Sản phẩm của bài thực hành gồm hợp đồng đo, bảng phân loại 10 tài khoản ban đầu, danh mục đường, tham chiếu bằng chứng giả lập và danh sách hành động có owner. Các kết quả phần trăm phải có thể tính lại từ những dữ liệu đó.

## 15. Tự kiểm tra cách hiểu

**Tất cả quản trị viên đã đăng ký MFA. Vì sao coverage thực thi vẫn có thể thấp?** Vì đăng ký chỉ chứng minh khả năng sử dụng phương thức. Chính sách có thể chưa áp dụng đúng phạm vi, còn đường trực tiếp hoặc thiếu bằng chứng cho một số đường.

**Một tài khoản có ba đường đạt và một đường không đạt được phân loại thế nào?** `GAP`. Đếm ba đường đạt không loại bỏ khả năng dùng đường còn lại để nhận quyền mà không đáp ứng MFA.

**Tài khoản không đăng nhập trong kỳ có được tính đạt không?** Không thể kết luận từ việc không đăng nhập. Tài khoản vẫn có thể thuộc mẫu số; cần đánh giá cấu hình, đường truy cập và bằng chứng còn hiệu lực theo định nghĩa.

**PAM không hỏi MFA mới nhưng nhận phiên từ IdP có MFA thì có được tính đạt không?** Có thể, nếu chuỗi bằng chứng xác minh mức bảo đảm, danh tính, ứng dụng, tuổi xác thực và ràng buộc phiên đều đáp ứng chính sách, đồng thời không có đường bỏ qua thuộc phạm vi. Không thể kết luận chỉ từ việc có hoặc không có màn hình thử thách.

**Ngoại lệ break-glass được phê duyệt có tăng tử số không?** Không tăng tử số MFA kỹ thuật nếu đường đó chưa đáp ứng MFA. Nó được báo cáo như gap có ngoại lệ còn hiệu lực và cần được quản lý theo cơ chế riêng.

**Tỷ lệ theo phiên cao hơn tỷ lệ theo tài khoản có phải lỗi tính toán không?** Không nhất thiết. Hai tỷ lệ có đơn vị và phân bố hoạt động khác nhau. Cần kiểm tra định nghĩa và dữ liệu gốc trước khi so sánh.

MFA coverage có giá trị khi người đọc đi được từ một tỷ lệ tới tập tài khoản, từ tài khoản tới các đường truy cập, và từ mỗi kết luận tới bằng chứng còn hiệu lực. Khi những liên kết đó rõ ràng, chỉ số trở thành cơ sở để xử lý khoảng trống bảo vệ truy cập đặc quyền thay vì chỉ là một con số về triển khai MFA.
