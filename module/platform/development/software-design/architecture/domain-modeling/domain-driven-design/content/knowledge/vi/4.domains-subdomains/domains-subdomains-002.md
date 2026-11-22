# Miền con cốt lõi (Core), hỗ trợ (Supporting) và phổ dụng (Generic)

Domain-Driven Design (DDD) xem hiểu biết về nghiệp vụ là nền tảng để thiết kế phần mềm. Khi khám phá một miền (domain), đội phát triển thường nhận ra rằng miền đó chứa nhiều nhóm vấn đề khác nhau. Có nhóm quyết định vì sao khách hàng chọn doanh nghiệp; có nhóm giúp doanh nghiệp vận hành và phục vụ nhóm vấn đề chính; cũng có nhóm là nhu cầu phổ biến mà nhiều tổ chức cùng gặp phải.

DDD gọi các nhóm vấn đề này là **subdomain (miền con)** và phân loại chúng thành ba loại: **Core Subdomain (miền con cốt lõi)**, **Supporting Subdomain (miền con hỗ trợ)** và **Generic Subdomain (miền con phổ dụng)**. Việc phân loại giúp doanh nghiệp và đội phát triển quyết định nên đầu tư năng lực chuyên môn ở đâu, phần nào cần mô hình hóa sâu, phần nào có thể đơn giản hóa hoặc sử dụng giải pháp có sẵn.

Ba loại này phản ánh giá trị chiến lược của một miền con đối với một doanh nghiệp trong một bối cảnh cụ thể. Chúng không phải mức độ quan trọng tuyệt đối, không phải thứ hạng chất lượng kỹ thuật và cũng không phải cách chia hệ thống thành ba tầng.

## 1. Domain, Subdomain và vị trí của việc phân loại

### 1.1. Domain là phạm vi vấn đề doanh nghiệp cần giải quyết

Domain (miền nghiệp vụ) là lĩnh vực hoạt động và hệ thống kiến thức mà doanh nghiệp cần hiểu để đạt được mục tiêu. Ví dụ, miền của một doanh nghiệp phân phối linh kiện công nghiệp có thể bao gồm tìm đúng linh kiện thay thế, quản lý nhà cung cấp, báo giá, xử lý đơn hàng, giao hàng và chăm sóc khách hàng.

Một miền lớn thường quá rộng để mô hình hóa như một khối duy nhất. Những bộ phận khác nhau có mục tiêu, thuật ngữ, quy tắc và cách ra quyết định khác nhau. Vì vậy, cần phân rã miền thành các subdomain có phạm vi vấn đề nhỏ hơn.

### 1.2. Subdomain là một phần vấn đề nghiệp vụ

Subdomain là một vùng kiến thức và trách nhiệm nghiệp vụ có thể được nhận diện trong domain. Mỗi miền con giải quyết một nhóm vấn đề tương đối rõ.

Ví dụ với doanh nghiệp phân phối linh kiện:

- Xác định linh kiện nào tương thích với máy móc của khách hàng.
- Quản lý thông tin và quan hệ với nhà cung cấp.
- Xử lý báo giá và đơn đặt hàng.
- Quản lý tài khoản người dùng.
- Gửi thông báo về trạng thái giao hàng.

Đây là các nhóm vấn đề nghiệp vụ. Chúng không nhất thiết tương ứng với một phòng ban, một ứng dụng hoặc một cơ sở dữ liệu.

### 1.3. Ba loại miền con trả lời câu hỏi về giá trị chiến lược

Phân loại Core, Supporting và Generic giúp trả lời câu hỏi:

- Năng lực nào tạo ra sự khác biệt khiến khách hàng chọn doanh nghiệp?
- Năng lực nào cần thiết để cung cấp giá trị nhưng không phải lý do chính khiến khách hàng chọn doanh nghiệp?
- Nhu cầu nào phổ biến, đã có giải pháp tiêu chuẩn trên thị trường và không cần doanh nghiệp tự tạo lợi thế riêng?

Có thể hình dung:

~~~text
DOMAIN: Phân phối linh kiện công nghiệp
|
+-- CORE: Tìm linh kiện tương thích và cam kết khả năng cung ứng
|
+-- SUPPORTING: Quản lý dữ liệu nhà cung cấp, xử lý nghiệp vụ báo giá
|
+-- GENERIC: Đăng nhập, gửi email, quản lý tài khoản cơ bản
~~~

Sơ đồ chỉ minh họa một cách phân loại có thể xảy ra. Một doanh nghiệp khác trong cùng ngành có thể có chiến lược và cách phân loại khác.

### 1.4. Phân biệt Subdomain với Bounded Context

Hai khái niệm này thường được nhắc cùng nhau trong strategic design của DDD, nhưng chúng trả lời hai câu hỏi khác nhau:

| Khái niệm | Trả lời câu hỏi | Bản chất |
|---|---|---|
| Subdomain | Doanh nghiệp cần giải quyết những nhóm vấn đề nghiệp vụ nào? | Phạm vi vấn đề trong domain |
| Bounded Context | Một mô hình và ngôn ngữ cụ thể có hiệu lực trong ranh giới nào? | Ranh giới của mô hình trong giải pháp phần mềm |

Subdomain thuộc problem space (không gian vấn đề). Bounded Context thuộc solution space (không gian giải pháp). Việc nhận diện subdomain giúp hiểu cấu trúc nghiệp vụ; việc xác định bounded context giúp tổ chức mô hình và mã nguồn sao cho các thuật ngữ, quy tắc không xung đột.

Một subdomain có thể được triển khai bằng một hoặc nhiều bounded context. Một bounded context cũng có thể bao quát một phạm vi nghiệp vụ rộng tùy cách tổ chức mô hình. Không nên áp đặt quy tắc máy móc rằng mỗi subdomain luôn phải có đúng một bounded context.

Việc phân loại Core, Supporting hay Generic áp dụng cho subdomain. Bounded context có thể chứa mô hình phục vụ một subdomain, nhưng bản thân khái niệm bounded context không phải một loại thứ tư của subdomain.

## 2. Core Subdomain — Miền con cốt lõi

### 2.1. Định nghĩa

Core Subdomain là phần nghiệp vụ tạo nên lợi thế cạnh tranh hoặc năng lực khác biệt quan trọng của doanh nghiệp. Đây thường là nơi chứa kiến thức, quy tắc, thuật toán, kinh nghiệm hoặc cách tổ chức công việc khiến sản phẩm và dịch vụ của doanh nghiệp có giá trị riêng.

Khách hàng có thể chọn doanh nghiệp vì năng lực này. Đối thủ khó sao chép hoàn toàn vì nó dựa trên dữ liệu, kinh nghiệm, quy trình, quan hệ hoặc tri thức tích lũy trong thời gian dài.

Ví dụ:

- Một nền tảng tuyển dụng có thuật toán và quy trình ghép ứng viên với công việc phù hợp tạo ra kết quả tốt hơn đối thủ.
- Một công ty logistics có khả năng tối ưu tuyến giao hàng theo đặc thù hàng hóa, địa hình và cam kết thời gian.
- Một doanh nghiệp bảo hiểm có năng lực đánh giá rủi ro chuyên biệt cho một nhóm khách hàng.
- Một nhà phân phối linh kiện có tri thức xác định linh kiện thay thế tương thích với nhiều đời máy, kể cả khi dữ liệu nhà sản xuất không đầy đủ.

### 2.2. Dấu hiệu nhận diện

Một miền con có thể là Core nếu nhiều dấu hiệu sau xuất hiện:

**Tạo ra sự khác biệt trên thị trường.** Năng lực này ảnh hưởng rõ đến lý do khách hàng chọn doanh nghiệp, mức độ hài lòng, tỷ lệ chuyển đổi, khả năng giữ chân hoặc mức giá doanh nghiệp có thể đưa ra.

**Gắn với mục tiêu chiến lược.** Ban lãnh đạo xem năng lực này là một phần trọng tâm của kế hoạch tăng trưởng, định vị sản phẩm hoặc chiến lược cạnh tranh.

**Chứa tri thức riêng.** Quy tắc và quyết định phụ thuộc vào hiểu biết tích lũy, dữ liệu độc quyền, kinh nghiệm chuyên gia hoặc cách vận hành mà đối thủ khó có ngay.

**Cần được thay đổi để thích nghi.** Khi thị trường, khách hàng hoặc đối thủ thay đổi, doanh nghiệp cần liên tục cải tiến năng lực này.

**Khó thay thế bằng một sản phẩm tiêu chuẩn.** Một giải pháp có sẵn có thể cung cấp chức năng cơ bản nhưng không đáp ứng được logic tạo nên lợi thế riêng.

Không cần tất cả dấu hiệu đều xuất hiện. Hãy xem chúng là bằng chứng để thảo luận với chuyên gia và người chịu trách nhiệm chiến lược.

### 2.3. Ví dụ: xác định linh kiện thay thế tương thích

Giả sử một nhà phân phối cung cấp linh kiện cho nhà máy. Khách hàng thường không chỉ hỏi “có sản phẩm mã X không?” mà còn cần biết linh kiện đó có thay thế an toàn cho thiết bị đang sử dụng hay không.

Đội ngũ chuyên gia có thể dựa vào:

- Hãng và dòng máy.
- Phiên bản thiết bị hoặc năm sản xuất.
- Thông số kỹ thuật và điều kiện vận hành.
- Quan hệ tương thích giữa các mã linh kiện.
- Những giới hạn khi thay thế.
- Kinh nghiệm từ các trường hợp lắp đặt trước đây.

Nếu doanh nghiệp có tri thức tương thích tốt hơn đối thủ, có thể đề xuất đúng sản phẩm, giảm thời gian dừng máy và tăng độ tin cậy. Năng lực này có thể là Core Subdomain vì nó trực tiếp tạo ra lý do khách hàng chọn nhà phân phối.

Chức năng tra cứu mã sản phẩm đơn thuần chưa chắc là Core. Giá trị cốt lõi nằm ở khả năng đưa ra kết luận phù hợp với ngữ cảnh sử dụng, cùng các quy tắc và bằng chứng hỗ trợ kết luận đó.

### 2.4. Cách đầu tư vào Core Subdomain

Doanh nghiệp nên dành chuyên gia nghiệp vụ, kỹ sư giỏi và thời gian cải tiến cho miền con cốt lõi. Đội phát triển cần hiểu sâu quy tắc thay vì chỉ chuyển các biểu mẫu hiện tại thành màn hình và API.

Các định hướng thường phù hợp:

- Làm việc trực tiếp và thường xuyên với chuyên gia miền.
- Xây dựng ngôn ngữ chung (Ubiquitous Language) cho phạm vi mô hình.
- Thiết kế mô hình phản ánh các khái niệm, quyết định và quy tắc quan trọng.
- Phát triển theo vòng lặp ngắn, kiểm chứng bằng tình huống nghiệp vụ.
- Giữ khả năng thay đổi logic cốt lõi khi chiến lược hoặc thị trường thay đổi.
- Bảo vệ tri thức tạo khác biệt bằng cách quản lý dữ liệu, quy tắc và quyền truy cập phù hợp.

Core Subdomain thường xứng đáng được đầu tư phần mềm riêng khi giải pháp đó giúp doanh nghiệp duy trì hoặc tăng lợi thế cạnh tranh. Tuy nhiên, “Core” không đồng nghĩa với việc phải tự viết mọi thư viện, hạ tầng hoặc chức năng kỹ thuật hỗ trợ nó.

## 3. Supporting Subdomain — Miền con hỗ trợ

### 3.1. Định nghĩa

Supporting Subdomain là phần nghiệp vụ cần thiết để doanh nghiệp vận hành và hỗ trợ Core Subdomain tạo ra giá trị. Nó thường chứa quy tắc riêng của doanh nghiệp, nhưng bản thân nó không tạo ra sự khác biệt cạnh tranh đáng kể.

Nếu thiếu miền con hỗ trợ, hoạt động cốt lõi có thể bị gián đoạn hoặc trở nên kém hiệu quả. Tuy nhiên, làm tốt miền con này thường không phải lý do chính khiến khách hàng lựa chọn doanh nghiệp thay vì đối thủ.

Ví dụ:

- Quy trình tiếp nhận và xác minh hồ sơ nhà cung cấp theo chính sách nội bộ.
- Quản lý yêu cầu hỗ trợ khách hàng theo cách tổ chức riêng.
- Điều phối tác vụ nội bộ giữa bộ phận kinh doanh và kho.
- Quản lý một quy trình phê duyệt đặc thù phục vụ hoạt động bán hàng.

### 3.2. Dấu hiệu nhận diện

**Cần thiết cho hoạt động kinh doanh.** Nếu bỏ đi, quy trình cốt lõi gặp trở ngại, tăng chi phí hoặc không thể hoạt động đầy đủ.

**Có logic riêng nhưng ít tạo khác biệt.** Quy tắc có thể đặc thù với doanh nghiệp, song khách hàng thường không chọn nhà cung cấp chỉ vì năng lực này.

**Có thể đơn giản hóa.** Nhiều bước có thể được chuẩn hóa, giảm biến thể hoặc thay bằng quy trình vận hành ít phức tạp hơn.

**Không cần đầu tư cạnh tranh ở mức cao nhất.** Doanh nghiệp vẫn cần chất lượng phù hợp, nhưng không nhất thiết dành nguồn lực nghiên cứu và phát triển lớn như với Core Subdomain.

### 3.3. Ví dụ: quản lý hồ sơ nhà cung cấp

Nhà phân phối linh kiện cần thu thập thông tin nhà cung cấp, kiểm tra hồ sơ, lưu chứng từ, ghi nhận trạng thái hợp tác và chuyển yêu cầu phê duyệt cho người có thẩm quyền.

Quy trình này có thể chứa các quy tắc riêng:

- Loại hồ sơ cần có theo nhóm nhà cung cấp.
- Ai được quyền phê duyệt.
- Điều kiện để chuyển nhà cung cấp sang trạng thái hoạt động.
- Khi nào cần rà soát lại hồ sơ.
- Cách xử lý khi chứng từ hết hạn.

Đây là nghiệp vụ có ý nghĩa và không thể bỏ qua. Tuy nhiên, nếu các đối thủ trong ngành đều có quy trình quản lý nhà cung cấp tương tự, việc tự phát triển một hệ thống cực kỳ khác biệt cho quy trình này có thể không mang lại giá trị tương xứng.

### 3.4. Cách xử lý Supporting Subdomain

Mục tiêu là đáp ứng đúng nhu cầu nghiệp vụ với chi phí và độ phức tạp hợp lý.

Có thể cân nhắc:

- Dùng quy trình chuẩn và hạn chế ngoại lệ không cần thiết.
- Tái sử dụng nền tảng hoặc thành phần nội bộ nếu phù hợp.
- Mua giải pháp chuyên dụng khi có sản phẩm đáp ứng tốt.
- Tự phát triển phần tùy chỉnh nhỏ nếu quy trình có đặc thù thực sự.
- Giữ mô hình đủ rõ để bảo toàn quy tắc và dữ liệu quan trọng.
- Tạo giao diện tích hợp ổn định với Core Subdomain.

Supporting không có nghĩa là làm sơ sài. Một quy trình hỗ trợ sai có thể khiến dữ liệu cốt lõi không đáng tin cậy hoặc làm nhân viên không thể phục vụ khách hàng. Mức đầu tư cần phù hợp với tác động và rủi ro của nó.

## 4. Generic Subdomain — Miền con phổ dụng

### 4.1. Định nghĩa

Generic Subdomain là nhóm vấn đề phổ biến mà nhiều doanh nghiệp cùng gặp phải và thường đã có giải pháp tiêu chuẩn trên thị trường. Doanh nghiệp thường không tạo lợi thế cạnh tranh đáng kể bằng cách tự phát triển lại những chức năng này.

Ví dụ:

- Xác thực người dùng theo cơ chế tiêu chuẩn.
- Gửi email hoặc tin nhắn thông báo.
- Quản lý lịch làm việc cơ bản.
- Xử lý thanh toán thông qua nhà cung cấp dịch vụ phổ biến.
- Các chức năng kế toán hoặc quản trị nhân sự tiêu chuẩn, tùy phạm vi và chiến lược doanh nghiệp.

Generic không có nghĩa là không quan trọng hoặc không có rủi ro. Một dịch vụ xác thực, thanh toán hay kế toán có thể ảnh hưởng lớn đến hoạt động. Tính “phổ dụng” nói về mức độ khác biệt chiến lược và khả năng mua hoặc áp dụng giải pháp chung, không nói rằng doanh nghiệp có thể bỏ qua chất lượng, bảo mật hay tuân thủ.

### 4.2. Dấu hiệu nhận diện

**Nhiều tổ chức có cùng nhu cầu.** Vấn đề không riêng biệt với doanh nghiệp đang xét.

**Có cách giải quyết đã được chuẩn hóa.** Quy trình, giao thức hoặc sản phẩm trên thị trường đã tương đối trưởng thành.

**Không phải năng lực tạo khác biệt chính.** Khách hàng thường kỳ vọng chức năng đó hoạt động đúng, nhưng ít khi chọn doanh nghiệp chỉ vì cách doanh nghiệp triển khai nó.

**Chi phí tự phát triển thường khó biện minh.** Xây dựng lại có thể tiêu tốn thời gian và nguồn lực mà không làm tăng lợi thế cạnh tranh tương xứng.

### 4.3. Ví dụ: xác thực tài khoản

Một nền tảng B2B cần cho người dùng đăng nhập, đăng xuất, đặt lại mật khẩu và quản lý phiên. Đây là nhu cầu phổ biến. Nếu doanh nghiệp không có yêu cầu xác thực đặc biệt tạo nên lợi thế riêng, việc sử dụng một nhà cung cấp Identity hoặc giải pháp tiêu chuẩn có thể hợp lý hơn tự phát triển toàn bộ.

Dù sử dụng dịch vụ có sẵn, doanh nghiệp vẫn cần xác định:

- Ai được phép truy cập hệ thống nào.
- Vai trò và quyền nghiệp vụ được quản lý ở đâu.
- Cách xử lý tài khoản bị khóa hoặc nhân viên nghỉ việc.
- Cách bảo vệ thông tin và đáp ứng yêu cầu bảo mật.
- Cách xử lý khi nhà cung cấp xác thực không khả dụng.

Nhà cung cấp có thể giải quyết xác thực danh tính, nhưng không tự động hiểu quyền nghiệp vụ riêng của doanh nghiệp. Cần phân định rõ phần tiêu chuẩn được cung cấp và phần chính sách thuộc domain của doanh nghiệp.

### 4.4. Cách xử lý Generic Subdomain

Các lựa chọn thường gặp:

- Mua hoặc thuê dịch vụ có sẵn.
- Dùng sản phẩm tiêu chuẩn hoặc SaaS.
- Tích hợp thư viện hoặc nền tảng đã được kiểm chứng.
- Áp dụng quy trình chuẩn thay vì tùy chỉnh quá nhiều.
- Giới hạn phần mã tùy biến quanh giải pháp bên ngoài.
- Thiết kế cách tích hợp để có thể thay thế nhà cung cấp khi cần.

Không nên tự xây dựng một hệ thống lớn chỉ vì đội kỹ thuật muốn kiểm soát mọi thứ. Tuy nhiên, cũng không nên chọn giải pháp có sẵn một cách máy móc. Cần đánh giá chi phí dài hạn, bảo mật, tuân thủ, khả năng tích hợp, mức độ phụ thuộc nhà cung cấp và tác động khi dịch vụ ngừng hoạt động.

## 5. So sánh ba loại Subdomain

| Tiêu chí | Core | Supporting | Generic |
|---|---|---|---|
| Giá trị chiến lược | Tạo lợi thế cạnh tranh chính | Hỗ trợ năng lực cốt lõi | Ít hoặc không tạo khác biệt |
| Quan hệ với khách hàng | Có thể là lý do khách hàng lựa chọn | Giúp cung cấp dịch vụ tốt | Thường là kỳ vọng tiêu chuẩn |
| Tri thức nghiệp vụ | Độc đáo, tích lũy, khó sao chép | Có đặc thù doanh nghiệp | Phổ biến, có thể chuẩn hóa |
| Mức độ đầu tư khác biệt | Cao | Vừa đủ theo nhu cầu | Ưu tiên hiệu quả và tiêu chuẩn |
| Hướng giải pháp thường cân nhắc | Tự xây dựng và cải tiến | Đơn giản hóa, tùy chỉnh vừa phải hoặc mua | Mua, thuê, dùng sản phẩm tiêu chuẩn |
| Mức độ mô hình hóa | Sâu vào quy tắc tạo giá trị | Đủ rõ cho nghiệp vụ và tích hợp | Tập trung hợp đồng, cấu hình và tích hợp |
| Câu hỏi chiến lược | Điều gì khiến khách hàng chọn chúng ta? | Điều gì giúp năng lực cốt lõi vận hành? | Có giải pháp chung đáng tin cậy nào? |

Không nên dùng bảng này như một công thức chấm điểm tự động. Một miền con có thể có một số đặc điểm của nhiều loại. Điều quan trọng là thảo luận về giá trị chiến lược, bằng chứng và quyết định đầu tư.

## 6. Ví dụ phân loại trong một doanh nghiệp phân phối linh kiện

Giả sử doanh nghiệp A phân phối linh kiện công nghiệp cho nhà máy. Doanh nghiệp cạnh tranh bằng khả năng xác định đúng linh kiện thay thế và đưa ra cam kết cung ứng đáng tin cậy. Khách hàng đánh giá cao việc giảm thời gian tìm kiếm, giảm lỗi đặt nhầm và hạn chế thời gian dừng máy.

Có thể phân rã domain như sau:

| Subdomain | Vấn đề nghiệp vụ | Phân loại giả định | Lý do |
|---|---|---|---|
| Tương thích linh kiện | Xác định linh kiện phù hợp với thiết bị và điều kiện sử dụng | Core | Tri thức chuyên sâu tạo khác biệt cho khách hàng |
| Cam kết khả năng cung ứng | Kết hợp tồn kho, thời gian nhập và mức độ tin cậy để đưa ra lời hứa giao hàng | Core | Ảnh hưởng trực tiếp đến độ tin cậy và quyết định mua |
| Quản lý hồ sơ nhà cung cấp | Thu thập, kiểm tra và phê duyệt hồ sơ | Supporting | Cần thiết cho hoạt động nhưng ít tạo khác biệt |
| Xử lý yêu cầu báo giá nội bộ | Chuyển yêu cầu, theo dõi phê duyệt và phản hồi | Supporting | Có quy trình riêng nhưng có thể chuẩn hóa |
| Xác thực tài khoản | Đăng nhập, đặt lại mật khẩu, quản lý phiên | Generic | Nhu cầu phổ biến, có giải pháp tiêu chuẩn |
| Gửi email thông báo | Gửi xác nhận và cập nhật trạng thái | Generic | Hạ tầng phổ biến, không phải lợi thế cạnh tranh |

Bảng trên là giả định dựa trên chiến lược đã nêu. Nếu doanh nghiệp A cạnh tranh chủ yếu bằng dịch vụ tài chính cho nhà cung cấp, một năng lực đang được xếp Supporting có thể trở thành Core. Nếu doanh nghiệp đầu tư mạnh vào nền tảng giao tiếp khách hàng độc quyền, một phần năng lực thông báo có thể có giá trị chiến lược riêng. Phân loại cần theo chiến lược thực tế, không theo tên chức năng.

### 6.1. Theo dõi một yêu cầu từ khách hàng

Khách hàng gửi yêu cầu tìm linh kiện thay thế cho một máy công nghiệp đã sử dụng nhiều năm.

1. Hệ thống xác thực tài khoản người gửi. Đây có thể là Generic Subdomain.
2. Yêu cầu được ghi nhận và chuyển cho nhân viên phụ trách. Quy trình điều phối có thể là Supporting Subdomain.
3. Chuyên gia đối chiếu model máy, thông số và lịch sử thay thế để xác định linh kiện phù hợp. Đây có thể là Core Subdomain.
4. Hệ thống kiểm tra tồn kho và thời gian nhập để đưa ra cam kết cung ứng. Nếu đây là năng lực tạo khác biệt của doanh nghiệp, nó cũng có thể thuộc Core.
5. Hệ thống gửi email thông báo cho khách hàng. Đây thường là Generic Subdomain.

Luồng công việc cho thấy một giao dịch có thể đi qua nhiều subdomain khác nhau. Một chức năng hướng tới người dùng không nhất thiết thuộc cùng một loại với toàn bộ quy trình.

## 7. Quy trình xác định loại Subdomain

Phân loại tốt cần kết hợp hiểu biết nghiệp vụ, chiến lược và bằng chứng thực tế. Có thể tiến hành theo các bước sau.

### Bước 1: Xác định mục tiêu và domain

Làm rõ doanh nghiệp phục vụ nhóm khách hàng nào, giải quyết vấn đề gì và muốn đạt kết quả nào. Nếu phạm vi domain chưa rõ, việc đánh giá một miền con có tạo khác biệt hay không sẽ thiếu cơ sở.

Câu hỏi gợi ý:

- Khách hàng thuê hoặc mua sản phẩm để giải quyết vấn đề nào?
- Doanh nghiệp muốn được thị trường biết đến vì năng lực gì?
- Những kết quả nào quyết định thành công của chiến lược?
- Doanh nghiệp đang cạnh tranh bằng giá, tốc độ, chất lượng, độ tin cậy hay tri thức chuyên môn?

### Bước 2: Phân rã domain thành các Subdomain

Trao đổi với chuyên gia và người trực tiếp thực hiện để nhận diện các nhóm vấn đề. Có thể dùng bản đồ năng lực nghiệp vụ (business capability map), sơ đồ quy trình hoặc danh sách trách nhiệm để bắt đầu.

Đặt tên miền con bằng ngôn ngữ nghiệp vụ, mô tả mục đích và phạm vi. Tránh chia theo tên màn hình, bảng dữ liệu, dịch vụ kỹ thuật hoặc sơ đồ tổ chức hiện tại.

### Bước 3: Tìm năng lực tạo khác biệt

Với từng miền con, hỏi:

- Khách hàng có nhận thấy sự khác biệt khi doanh nghiệp làm tốt phần này không?
- Phần này có ảnh hưởng đến lý do khách hàng chọn hoặc tiếp tục sử dụng dịch vụ không?
- Đối thủ có thể dễ dàng mua hoặc sao chép năng lực tương đương không?
- Tri thức hoặc dữ liệu nào khiến doanh nghiệp có ưu thế?
- Chiến lược tương lai có phụ thuộc vào việc cải tiến miền con này không?

Những câu trả lời có bằng chứng mạnh về khác biệt chiến lược là dấu hiệu của Core Subdomain.

### Bước 4: Xác định phần hỗ trợ và phần phổ dụng

Với miền con chưa phải Core, tiếp tục hỏi:

- Nếu không có năng lực này, hoạt động cốt lõi bị ảnh hưởng thế nào?
- Quy tắc có đặc thù với doanh nghiệp hay phổ biến trong nhiều tổ chức?
- Có sản phẩm tiêu chuẩn nào giải quyết tốt vấn đề không?
- Phần nào cần tùy chỉnh để phù hợp quy trình riêng?
- Chi phí sở hữu và rủi ro của giải pháp mua sẵn là gì?

Miền con có logic hỗ trợ riêng nhưng không tạo khác biệt thường phù hợp với Supporting. Miền con có nhu cầu phổ biến và giải pháp tiêu chuẩn phù hợp có thể là Generic.

### Bước 5: Ghi lại bằng chứng và mức độ tin cậy

Không nên phân loại chỉ dựa trên cảm nhận của một người. Hãy ghi rõ lý do, người xác nhận và bằng chứng.

Ví dụ, nhận định “khả năng tìm linh kiện tương thích là Core” có thể được hỗ trợ bởi:

- Phỏng vấn khách hàng cho thấy đây là lý do họ chọn doanh nghiệp.
- Dữ liệu cho thấy yêu cầu có tư vấn tương thích có tỷ lệ chuyển đổi cao hơn.
- Chuyên gia giải thích tri thức tích lũy qua nhiều năm.
- Đối thủ chưa cung cấp được kết quả tương đương.
- Kế hoạch sản phẩm xác định năng lực này là ưu tiên chiến lược.

Nếu chưa có đủ bằng chứng, ghi trạng thái giả thuyết và lên kế hoạch xác minh.

### Bước 6: Xác nhận với các bên liên quan

Thảo luận kết quả với lãnh đạo sản phẩm, chuyên gia miền, kiến trúc sư và đại diện đội vận hành. Mỗi nhóm nhìn thấy một phần khác nhau của giá trị và chi phí.

Khi có bất đồng, hãy tìm hiểu điều kiện hoặc mục tiêu đang khác nhau. Một năng lực có thể là Core đối với chiến lược của đơn vị kinh doanh này nhưng chỉ là Generic đối với đơn vị khác.

### Bước 7: Chuyển kết quả thành quyết định đầu tư

Phân loại chỉ hữu ích khi nó dẫn đến quyết định cụ thể:

- Đội nào cần sở hữu tri thức và mô hình?
- Phần nào cần đầu tư phát triển dài hạn?
- Phần nào có thể chuẩn hóa?
- Phần nào nên mua hoặc thuê?
- Ranh giới tích hợp và trách nhiệm giữa các nhóm là gì?
- Rủi ro nào cần quản lý nếu phụ thuộc nhà cung cấp?

## 8. Ảnh hưởng của phân loại đến thiết kế và tổ chức phát triển

### 8.1. Đối với Core Subdomain

Core cần đội ngũ hiểu nghiệp vụ sâu và có quyền cải tiến mô hình. Chuyên gia miền nên tham gia thường xuyên vào việc khám phá quy tắc, đánh giá ví dụ và xác nhận hành vi phần mềm.

Thiết kế cần làm nổi bật các khái niệm và quy tắc quan trọng. Đội phát triển nên ưu tiên kiểm thử những quyết định có ảnh hưởng đến lợi thế cạnh tranh, đồng thời tránh để logic cốt lõi bị phân tán qua nhiều hệ thống khó kiểm soát.

Core thường là nơi đáng đầu tư vào mô hình miền phong phú (rich domain model) nếu nghiệp vụ có quy tắc và hành vi phức tạp. Tuy nhiên, không phải mọi Core Subdomain đều cần cùng một mức độ phức tạp kỹ thuật. Mô hình phải phản ánh vấn đề thực tế.

### 8.2. Đối với Supporting Subdomain

Supporting cần mô hình đủ để biểu diễn quy tắc đặc thù, trạng thái và trách nhiệm. Có thể chọn giải pháp đơn giản, ít tùy chỉnh, dễ bảo trì.

Nếu quy trình hỗ trợ có nhiều ngoại lệ do cách tổ chức nội bộ, cần cân nhắc liệu các ngoại lệ đó có thật sự cần thiết hay có thể thay đổi quy trình. Đơn giản hóa nghiệp vụ đôi khi tạo ra giá trị lớn hơn việc thêm nhiều lớp kỹ thuật.

### 8.3. Đối với Generic Subdomain

Generic thường phù hợp với sản phẩm tiêu chuẩn, thư viện, dịch vụ SaaS hoặc hệ thống bên thứ ba. Đội phát triển tập trung vào cách tích hợp, cấu hình, dữ liệu trao đổi và xử lý sự cố.

Cần tránh tùy biến quá sâu một sản phẩm tiêu chuẩn nếu tùy biến khiến việc nâng cấp và thay nhà cung cấp trở nên khó khăn. Nếu có logic riêng của doanh nghiệp, hãy giữ logic đó trong mô hình thuộc phạm vi nghiệp vụ phù hợp thay vì nhồi toàn bộ vào sản phẩm Generic.

### 8.4. Phân loại giúp phân bổ năng lực, không thay thế quản trị chất lượng

Core, Supporting và Generic không tạo ra ba mức chất lượng phần mềm. Mọi miền con vẫn cần bảo mật, độ tin cậy, khả năng vận hành và dữ liệu chính xác theo mức rủi ro.

Một dịch vụ thanh toán Generic vẫn có thể là hệ thống có mức độ quan trọng vận hành rất cao. Doanh nghiệp phải có phương án giám sát, đối soát, xử lý lỗi và khôi phục. Tương tự, một quy trình Supporting có thể chịu yêu cầu tuân thủ nghiêm ngặt.

Phân loại giúp quyết định nơi cần tạo khác biệt và nơi nên tận dụng tiêu chuẩn. Nó không cho phép bỏ qua trách nhiệm kỹ thuật và vận hành.

## 9. Quan hệ giữa Subdomain, Bounded Context và Context Map

Sau khi hiểu các miền con và mức độ chiến lược, đội phát triển có thể tiếp tục xác định bounded context phù hợp cho từng mô hình.

Ví dụ, doanh nghiệp phân phối linh kiện có thể có các bounded context:

- **Product Compatibility:** mô hình hóa thiết bị, thông số và quy tắc tương thích.
- **Supplier Management:** mô hình hóa hồ sơ, trạng thái và điều kiện hợp tác với nhà cung cấp.
- **Identity Access:** quản lý danh tính và xác thực người dùng.
- **Order Fulfillment:** mô hình hóa việc tiếp nhận, xử lý và cam kết thực hiện đơn hàng.

Tên và ranh giới trên chỉ là ví dụ. Cần xác nhận bằng ngôn ngữ, quy tắc và trách nhiệm thực tế.

Một số điểm cần lưu ý:

- Core Subdomain có thể được triển khai qua nhiều bounded context nếu có các mô hình và trách nhiệm khác nhau.
- Một bounded context cần có ngôn ngữ và mô hình nhất quán; không nên gộp các khái niệm khác nghĩa chỉ để giảm số lượng dịch vụ.
- Generic Subdomain thường có thể được đáp ứng bởi một hệ thống bên ngoài, nhưng vẫn cần xác định cách hệ thống đó tương tác với mô hình nội bộ.
- Context Map mô tả quan hệ và cách tích hợp giữa các bounded context; nó không phải bản đồ phân loại Core, Supporting, Generic.

Khi một bounded context bên ngoài cung cấp mô hình không phù hợp với ngôn ngữ nội bộ, đội phát triển có thể cần lớp chống ăn mòn (Anti-Corruption Layer) để chuyển đổi và bảo vệ mô hình miền của mình. Đây là quyết định ở cấp độ tích hợp giữa các mô hình, không phải quy tắc bắt buộc cho mọi Generic Subdomain.

## 10. Phân loại có thể thay đổi theo thời gian

Một miền con không mang nhãn Core, Supporting hoặc Generic vĩnh viễn. Chiến lược, thị trường, công nghệ và năng lực nội bộ có thể thay đổi.

**Supporting trở thành Core.** Doanh nghiệp bắt đầu cạnh tranh bằng dịch vụ hậu mãi chuyên sâu. Năng lực xử lý bảo hành và dự đoán lỗi trước đây chỉ hỗ trợ bán hàng nay trở thành lý do khách hàng lựa chọn.

**Generic trở thành Core.** Một năng lực vốn phổ biến có thể được doanh nghiệp biến thành lợi thế nhờ dữ liệu, quy trình hoặc cách triển khai độc đáo. Ví dụ, hoạt động thanh toán tiêu chuẩn có thể được mở rộng thành mô hình tài chính đặc thù cho một ngành.

**Core trở nên ít khác biệt hơn.** Khi công nghệ hoặc dịch vụ tiêu chuẩn làm cho năng lực từng độc quyền trở nên phổ biến, doanh nghiệp có thể giảm đầu tư riêng và tập trung vào năng lực mới.

Vì vậy, nên rà soát phân loại khi:

- Chiến lược kinh doanh thay đổi.
- Doanh nghiệp bước vào phân khúc khách hàng mới.
- Đối thủ có năng lực tương đương.
- Một sản phẩm tiêu chuẩn mới xuất hiện.
- Công nghệ làm thay đổi chi phí và khả năng triển khai.
- Dữ liệu khách hàng cho thấy yếu tố quyết định lựa chọn đã thay đổi.

## 11. Những sai lầm thường gặp

### Nhầm Core với phần có nhiều tính năng nhất

Số lượng chức năng hoặc độ lớn của mã nguồn không quyết định giá trị chiến lược. Một quy tắc nhỏ nhưng quyết định chất lượng tư vấn có thể là phần cốt lõi.

### Nhầm Core với phần tạo ra doanh thu trực tiếp

Một năng lực có thể không trực tiếp thu tiền nhưng lại là lý do khách hàng tin tưởng và mua sản phẩm. Ngược lại, một quy trình tạo doanh thu có thể chỉ là nghiệp vụ tiêu chuẩn.

### Coi mọi thứ quan trọng là Core

Nhiều miền con rất quan trọng cho vận hành nhưng không tạo khác biệt cạnh tranh. Nếu mọi thứ đều được gọi là Core, doanh nghiệp mất khả năng ưu tiên đầu tư.

### Coi Generic là không quan trọng

Giải pháp phổ dụng vẫn có thể gây thiệt hại lớn nếu ngừng hoạt động, rò rỉ dữ liệu hoặc xử lý sai. Cần quản lý rủi ro và chất lượng theo tác động thực tế.

### Phân loại theo phòng ban hoặc hệ thống hiện có

Một phòng ban có thể phụ trách nhiều subdomain thuộc các loại khác nhau. Một ứng dụng cũ cũng có thể chứa cả logic Core lẫn Generic. Cần phân loại theo vấn đề và giá trị nghiệp vụ, không theo sơ đồ tổ chức hay tên phần mềm.

### Mặc định mọi Generic đều phải mua

Một sản phẩm có sẵn có thể không đáp ứng yêu cầu pháp lý, bảo mật, tích hợp hoặc chi phí dài hạn. Hãy so sánh tổng chi phí sở hữu và rủi ro trước khi quyết định.

### Cố gắng phân loại quá sớm

Khi chưa hiểu khách hàng, chiến lược và quy tắc nghiệp vụ, nhãn Core hay Supporting chỉ là suy đoán. Hãy ghi nhận giả thuyết, tìm bằng chứng và điều chỉnh khi hiểu biết tốt hơn.

### Đồng nhất loại Subdomain với mức độ phức tạp kỹ thuật

Một Generic Subdomain có thể có yêu cầu kỹ thuật khó. Một Core Subdomain có thể có một phần chức năng đơn giản. Giá trị chiến lược và độ phức tạp kỹ thuật là hai trục đánh giá khác nhau.

## 12. Mẫu ghi nhận và bài tập phân loại

### 12.1. Mẫu ghi nhận Subdomain

Có thể sử dụng bảng sau trong buổi khám phá miền:

| Trường thông tin | Nội dung cần ghi |
|---|---|
| Tên Subdomain | Tên nghiệp vụ mà chuyên gia sử dụng |
| Mục tiêu | Vấn đề mà miền con giải quyết |
| Phạm vi | Đầu vào, kết quả và trách nhiệm chính |
| Khách hàng / bên liên quan | Ai nhận giá trị hoặc chịu tác động? |
| Quy tắc nổi bật | Các quyết định và điều kiện quan trọng |
| Giá trị chiến lược | Vì sao miền con quan trọng với doanh nghiệp? |
| Khác biệt cạnh tranh | Năng lực nào khiến doanh nghiệp tốt hơn đối thủ? |
| Giải pháp thị trường | Có sản phẩm tiêu chuẩn nào đáp ứng được? |
| Phân loại hiện tại | Core / Supporting / Generic / Chưa đủ bằng chứng |
| Bằng chứng | Dữ liệu, phỏng vấn, quyết định chiến lược |
| Mức độ tin cậy | Đã xác nhận / Giả thuyết / Cần tìm hiểu |
| Quyết định đầu tư | Tự xây dựng, chuẩn hóa, mua hoặc thuê |

### 12.2. Câu hỏi kiểm tra nhanh

Với mỗi miền con, hãy trả lời lần lượt:

1. Nếu doanh nghiệp làm phần này tốt hơn đối thủ, khách hàng có nhận thấy và lựa chọn doanh nghiệp vì điều đó không?
2. Năng lực này có phụ thuộc vào tri thức hoặc dữ liệu đặc thù không?
3. Nếu bỏ năng lực này, phần cốt lõi của doanh nghiệp có bị ảnh hưởng không?
4. Có giải pháp tiêu chuẩn đáng tin cậy nào trên thị trường không?
5. Doanh nghiệp cần đầu tư cải tiến phần này ở mức nào để thực hiện chiến lược?

Cách diễn giải gợi ý:

- Nếu năng lực tạo khác biệt chiến lược rõ rệt, đó là ứng viên Core.
- Nếu năng lực cần thiết và có quy tắc riêng nhưng không tạo khác biệt chính, đó là ứng viên Supporting.
- Nếu nhu cầu phổ biến và giải pháp tiêu chuẩn phù hợp, đó là ứng viên Generic.
- Nếu chưa có bằng chứng, giữ trạng thái chưa phân loại và tiếp tục khám phá.

Đây là cách định hướng thảo luận, không phải thuật toán tự động thay thế đánh giá của doanh nghiệp.

### 12.3. Bài tập: phân loại miền con cho một nền tảng đặt lịch khám

Một doanh nghiệp xây dựng nền tảng giúp người dùng tìm và đặt lịch tại các cơ sở khám chữa bệnh. Doanh nghiệp muốn cạnh tranh bằng khả năng tìm đúng chuyên khoa, chọn cơ sở phù hợp với nhu cầu và giảm tỷ lệ người dùng bỏ lỡ lịch hẹn.

Hãy xem xét các nhóm vấn đề sau:

- Tìm kiếm và gợi ý cơ sở khám phù hợp.
- Quản lý lịch trống và điều kiện đặt lịch của từng cơ sở.
- Quản lý hồ sơ và thông tin liên hệ cơ sở.
- Xác thực tài khoản người dùng.
- Gửi email hoặc tin nhắn nhắc lịch.
- Quản lý hóa đơn và báo cáo nội bộ.

Hãy tự phân loại từng miền con thành Core, Supporting hoặc Generic. Với mỗi lựa chọn, giải thích:

- Năng lực đó có tạo ra khác biệt cho khách hàng không?
- Nó có hỗ trợ trực tiếp mục tiêu cạnh tranh không?
- Có giải pháp tiêu chuẩn nào đáp ứng được không?
- Doanh nghiệp nên tự phát triển, chuẩn hóa hay mua dịch vụ?
- Cần thêm bằng chứng gì trước khi chốt phân loại?

Không có một đáp án cố định cho mọi nền tảng. Nếu doanh nghiệp cạnh tranh bằng chất lượng gợi ý cơ sở khám, năng lực tìm kiếm phù hợp có thể là Core. Nếu doanh nghiệp cạnh tranh bằng khả năng đồng bộ lịch trống chính xác theo thời gian thực, phần quản lý lịch có thể cũng là Core. Nếu doanh nghiệp chỉ dùng một dịch vụ email phổ biến, gửi email thường là Generic.

### 12.4. Đáp án tham khảo cho tình huống

| Miền con | Phân loại tham khảo | Lý do |
|---|---|---|
| Tìm kiếm và gợi ý cơ sở khám | Core | Có thể là năng lực khác biệt trực tiếp theo chiến lược đã nêu |
| Quản lý lịch trống và điều kiện đặt lịch | Core hoặc Supporting | Phụ thuộc việc độ chính xác và khả năng đồng bộ có phải lợi thế chính hay chỉ là năng lực hỗ trợ |
| Quản lý hồ sơ cơ sở | Supporting | Cần cho vận hành và duy trì dữ liệu dịch vụ |
| Xác thực tài khoản | Generic | Nhu cầu phổ biến, có giải pháp tiêu chuẩn |
| Gửi thông báo nhắc lịch | Generic hoặc Supporting | Gửi tin nhắn cơ bản là Generic; logic nhắc lịch đặc thù có thể thuộc Supporting |
| Hóa đơn và báo cáo nội bộ | Supporting hoặc Generic | Phụ thuộc quy tắc tài chính riêng và khả năng dùng sản phẩm tiêu chuẩn |

Điểm quan trọng của bài tập là biết giải thích lựa chọn dựa trên chiến lược và bằng chứng. Tên chức năng không tự quyết định loại subdomain.

## Kết luận

Core, Supporting và Generic Subdomain là cách phân loại các nhóm vấn đề nghiệp vụ theo giá trị chiến lược của chúng đối với doanh nghiệp. Core tạo nên khác biệt cạnh tranh và xứng đáng nhận đầu tư chuyên môn sâu. Supporting giúp năng lực cốt lõi vận hành hiệu quả với mức độ tùy chỉnh hợp lý. Generic giải quyết những nhu cầu phổ biến mà doanh nghiệp thường có thể đáp ứng bằng sản phẩm hoặc tiêu chuẩn có sẵn.

Trong DDD, phân loại không dừng ở việc gắn nhãn. Kết quả cần giúp doanh nghiệp xác định nơi cần giữ và phát triển tri thức, nơi nên đơn giản hóa, nơi nên mua giải pháp, cũng như cách tổ chức mô hình và ranh giới tích hợp. Khi chiến lược thay đổi, việc phân loại cũng cần được xem xét lại để thiết kế phần mềm tiếp tục phục vụ đúng mục tiêu kinh doanh.

