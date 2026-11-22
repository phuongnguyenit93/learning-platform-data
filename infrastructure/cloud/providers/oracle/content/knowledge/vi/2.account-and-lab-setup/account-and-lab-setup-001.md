# Đăng ký tài khoản và hiểu phạm vi Free Tier, trial, trả phí

## Mục tiêu và phạm vi

Trong chương **Tài khoản và môi trường thực hành** của module Oracle Cloud Infrastructure (OCI), bước đầu tiên là xác định bạn đang dùng loại tài khoản nào, được tạo tài nguyên gì và khi nào phải trả tiền. Đây là nền tảng để những bài thực hành tenancy, compartment, IAM, VCN, Compute, lưu trữ và cơ sở dữ liệu Oracle có thể triển khai có kiểm soát.

Sau bài học, bạn có thể:

- Chuẩn bị thông tin đăng ký, chọn home region và kiểm tra tài khoản sau khi kích hoạt.
- Phân biệt Always Free, Free Trial và tài khoản trả phí Pay As You Go.
- Phân loại tài nguyên có thể giữ lại khi trial hết hạn và tài nguyên phải xử lý trước đó.
- Lập một kế hoạch lab có giới hạn tài nguyên, theo dõi chi phí và phương án dựng lại.

Bài dùng chính sách công khai được đối chiếu ngày **20/11/2026**. Quyền lợi, vùng hỗ trợ và hạn mức có thể thay đổi; khi thực hành, đối chiếu tài liệu chính thức với thông tin subscription, usage và cấu hình trong chính tenancy của bạn. Không dùng một ảnh chụp hoặc một bài hướng dẫn cũ làm căn cứ duy nhất để kết luận tài nguyên miễn phí.

## 1. Hiểu ba khái niệm trước khi đăng ký

**Free Tier** là tên chương trình gồm hai phần: ưu đãi **Always Free** và đợt **Free Trial** có thời hạn. **Pay As You Go (PAYG)** là hình thức tài khoản trả phí theo mức sử dụng. Một tài khoản đang trial vẫn có thể dùng tài nguyên Always Free; khi chuyển sang PAYG, tài khoản vẫn có thể hưởng phần Always Free đủ điều kiện. Tham khảo [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/).

| Khái niệm | Bản chất | Cách dùng trong học tập |
| --- | --- | --- |
| Always Free | Một số mức sử dụng hoặc cấu hình được miễn phí theo điều kiện dịch vụ | Làm nền cho lab nhỏ, kiểm tra tổng mức sử dụng trước khi tạo thêm |
| Free Trial | Credit khuyến mại có hạn dùng để thử dịch vụ đủ điều kiện | Thử nghiệm có lịch kết thúc và có bản xuất dữ liệu |
| PAYG | Subscription trả phí theo mức sử dụng, vẫn có quyền lợi miễn phí đủ điều kiện | Dùng khi bài lab cần cấu hình ngoài phạm vi miễn phí và đã có dự toán |

Một con số chi phí đang bằng 0 chưa đủ chứng minh dịch vụ thuộc Always Free. Nó có thể đang được credit trial chi trả hoặc dữ liệu chi phí chưa cập nhật. Câu hỏi cần trả lời là: **cấu hình này được hưởng ưu đãi nào, trong phạm vi nào và đến thời điểm nào?**

### 1.1. Credit trial là khoản khuyến mại có giới hạn

Theo [tài liệu OCI Free Tier](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm), chương trình trial cung cấp **300 USD credit, có giá trị tối đa 30 ngày**, áp dụng cho dịch vụ đủ điều kiện. Trial kết thúc khi hết hạn hoặc credit được dùng hết, tùy điều kiện nào đến trước; ưu đãi còn phụ thuộc quốc gia và điều kiện đăng ký được nêu tại [trang Free Tier](https://www.oracle.com/cloud/free/).

Credit không phải tiền mặt có thể rút và cũng không phải ngân sách được cấp lại mỗi tháng. Khi lập kế hoạch, hãy ghi ngày kết thúc và số dư hiển thị trong Console thay vì tự mặc định tài khoản nào cũng có đúng một ưu đãi.

Ví dụ học tập: một lab thử cơ sở dữ liệu ngoài Always Free được lên lịch chạy hai giờ, xuất dữ liệu rồi xóa trong cùng buổi. Việc còn nhiều credit không phải lý do để giữ tài nguyên chạy đến ngày cuối.

### 1.2. Miễn phí có điều kiện theo từng tài nguyên

Khi kiểm tra một tài nguyên, đọc đồng thời:

1. **Dịch vụ và cấu hình:** loại máy, số OCPU, RAM, loại lưu trữ hoặc lựa chọn Always Free của cơ sở dữ liệu.
2. **Phạm vi ưu đãi:** tổng theo tenancy, theo tháng, theo vùng hay theo tài nguyên.
3. **Phần phụ thuộc:** boot volume, bản sao lưu, truyền dữ liệu và thành phần tích hợp.
4. **Phần đã sử dụng:** tài nguyên cũ vẫn có thể chiếm hạn mức dù lab hiện tại mới bắt đầu.

Trong OCI, *shape* là cấu hình Compute; boot volume là ổ đĩa khởi động của máy. Vì vậy, chọn đúng shape mới chỉ kiểm tra được một phần của lab.

## 2. Chuẩn bị thông tin và chọn home region

### 2.1. Những gì cần chuẩn bị

Chuẩn bị email bạn kiểm soát lâu dài, số điện thoại, thông tin liên hệ chính xác và phương thức thanh toán hợp lệ. Oracle cho phép một tài khoản Free Trial hoặc Always Free trên mỗi người. FAQ hiện nhận thẻ tín dụng và thẻ ghi nợ hoạt động như thẻ tín dụng; không nhận thẻ yêu cầu PIN, thẻ ảo, thẻ dùng một lần hoặc thẻ trả trước. Xem [FAQ Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/faq/).

Dùng mật khẩu riêng cho tài khoản cloud và lưu bằng trình quản lý mật khẩu. Không gửi mật khẩu, mã OTP, thông tin thẻ hoặc khóa riêng cho người hỗ trợ lab. Với tài khoản do trường hoặc công ty cấp, dùng thông tin truy cập do quản trị viên cung cấp thay vì tự đăng ký thêm tài khoản để lấy credit.

Việc xác minh thẻ có thể tạo **khoản giữ tiền tạm thời** (*authorization hold*). Khoản này khác với phí sử dụng dịch vụ; thời gian giải phóng phụ thuộc ngân hàng. Oracle mô tả cơ chế này trong [Managing Account Upgrades and Payment Method](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/changingpaymentmethod.htm). Kiểm tra trạng thái giao dịch với ngân hàng nếu cần, thay vì chỉ nhìn thông báo số dư giảm.

### 2.2. Home region là quyết định cần cân nhắc trước

Home region là vùng địa lý nơi tài khoản và tài nguyên định danh ban đầu được tạo. Oracle nêu rõ **không thể thay đổi home region sau khi đăng ký** trong [Managing Regions](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingregions.htm). Compute và Autonomous Database thuộc Always Free phải được tạo ở home region theo [tài liệu Free Tier](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm).

Trước khi chọn, đánh giá:

- Vùng nào thực tế xuất hiện trong biểu mẫu đăng ký và có dịch vụ cần học?
- Độ trễ từ nơi bạn truy cập có phù hợp với SSH, Console và ứng dụng thử nghiệm?
- Dữ liệu lab có yêu cầu nơi lưu trữ cụ thể từ tổ chức hay không?
- Tài liệu thực hành có đang dùng vùng hoặc Availability Domain khác với tài khoản của bạn?

Với người học ở Việt Nam, có thể đánh giá các vùng châu Á được cung cấp khi đăng ký, nhưng cần tự kiểm tra danh sách hiện tại. Khoảng cách địa lý gần không đảm bảo còn capacity của shape miễn phí. Không chọn một vùng chỉ vì một bài đăng nói rằng vùng đó luôn tạo được máy.

## 3. Quy trình đăng ký và xác minh lần đầu

Thực hiện theo [hướng dẫn Sign Up for the Free Oracle Cloud Promotion](https://docs.oracle.com/en-us/iaas/Content/GSG/Tasks/signingup_topic-Sign_Up_for_Free_Oracle_Cloud_Promotion.htm):

1. Bắt đầu từ [trang Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/) và chọn đăng ký.
2. Nhập quốc gia, họ tên, email; hoàn tất bước xác minh email.
3. Đặt mật khẩu, tên cloud account và chọn home region đã cân nhắc.
4. Điền địa chỉ, số điện thoại và hoàn tất bước xác minh được yêu cầu.
5. Thêm phương thức thanh toán; đọc điều khoản trước khi gửi yêu cầu trial.
6. Chờ tenancy được cấp, nhận thư chào mừng và đăng nhập OCI Console.

Tên cloud account giúp xác định tài khoản cloud khi đăng nhập. Sau khi vào được Console, hãy ghi nhận tên tenancy, home region, identity domain đang dùng và thông tin subscription để lần đăng nhập sau có thể xác định đúng môi trường. Lưu các thông tin này trong ghi chép cá nhân phù hợp; không đưa bí mật xác thực vào kho mã nguồn.

### 3.1. Xác minh tài khoản trước khi tạo máy

Chưa cần tạo Compute hay Database trong lần kiểm tra này. Mục tiêu là có bằng chứng rõ ràng về môi trường:

| Cần xác minh | Kết quả cần ghi nhận |
| --- | --- |
| Đăng nhập | Vào đúng tenancy, đúng người dùng, hoàn tất MFA được yêu cầu |
| Vùng | Biết home region và vùng đang chọn trên Console |
| Subscription | Biết tài khoản đang trial, Free Tier sau trial hay PAYG |
| Ưu đãi | Biết số dư credit và ngày hết hạn nếu đang có trial |
| Thanh toán | Phân biệt xác minh thẻ với nâng cấp tài khoản trả phí |
| Khả năng tạo tài nguyên | Biết nơi kiểm tra Limits, Quotas and Usage |

Tên và vị trí menu có thể thay đổi. Có thể tìm theo chức năng như Billing & Cost Management, subscription, Cost Analysis hoặc Limits, Quotas and Usage; đọc nội dung trang trước khi xác nhận một thao tác thay đổi tài khoản.

### 3.2. Hoàn tất bảo vệ truy cập

Hoàn thành đăng ký MFA theo chính sách đăng nhập của identity domain, lưu phương án khôi phục ở nơi phù hợp và thử đăng nhập lại trước khi kết thúc buổi thiết lập. Không vô hiệu hóa yêu cầu MFA chỉ để bỏ qua bước đăng nhập. Cơ chế MFA của Console được Oracle mô tả trong [IAM MFA](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/iam_security_topic-IAM_MFA.htm).

Đối với các bài lab sau, nên có người dùng hoặc nhóm được cấp quyền theo nhu cầu và một compartment dành cho lab. Tài khoản quản trị dùng cho quản lý định danh và thanh toán cần được bảo vệ riêng; tránh chia sẻ một thông tin đăng nhập quản trị cho cả lớp. Những cấu hình IAM chi tiết sẽ được thực hiện ở bài tương ứng.

## 4. Đọc phạm vi Always Free theo tài nguyên

Tại mốc đối chiếu của bài, [Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) mô tả:

| Thành phần | Quyền lợi được nêu trong tài liệu |
| --- | --- |
| Compute AMD | Tối đa hai VM dùng shape `VM.Standard.E2.1.Micro` |
| Compute Arm A1 | 1.500 OCPU-giờ và 9.000 GB-giờ RAM mỗi tháng cho `VM.Standard.A1.Flex`; tương đương tổng 2 OCPU và 12 GB RAM cho tenancy Always Free |
| Block Volume | 200 GB dùng chung cho boot volume và block volume thuộc phạm vi ưu đãi |

Các con số là tổng quyền lợi, không cấp lại cho từng VM hoặc compartment. Tài liệu cũng nêu VM Always Free nhàn rỗi có thể bị thu hồi. Vì vậy, lưu mã nguồn và dữ liệu cần giữ ở nơi phù hợp, đồng thời chuẩn bị cách dựng lại lab.

Ví dụ tính toán do bài học đặt ra: hai máy A1 cùng chạy 100 giờ, mỗi máy dùng 1 OCPU và 6 GB RAM, sẽ sử dụng:

```text
OCPU-giờ = (1 × 100) + (1 × 100) = 200
GB-giờ RAM = (6 × 100) + (6 × 100) = 1.200
```

Đây là cách cộng mức sử dụng của nhiều máy, chưa phải kết luận toàn bộ lab được miễn phí. Bạn vẫn phải kiểm tra thời gian chạy còn lại trong tháng và các thành phần lưu trữ, mạng đi kèm.

Một lab Java có thể gồm VM chạy ứng dụng, volume chứa hệ điều hành, bucket giữ dữ liệu thử và một cơ sở dữ liệu. Hãy lập danh sách từng thành phần trước khi triển khai. Việc VM đủ điều kiện không tự chứng minh cơ sở dữ liệu hoặc mọi lựa chọn trong cùng màn hình tạo tài nguyên cũng đủ điều kiện.

Đối với Database, kiểm tra lựa chọn Always Free và giới hạn được hiển thị trong quy trình tạo. Không suy rộng rằng mọi dịch vụ mang tên Oracle Database, mọi cấu hình Autonomous Database hoặc mọi lựa chọn nâng cấp đều nằm trong phần miễn phí.

## 5. Phân biệt quyền tạo, hạn mức, quota và capacity

Không tạo được tài nguyên chưa chắc do hết credit. Hãy phân biệt các lớp sau:

| Lớp kiểm soát | Câu hỏi cần trả lời | Hướng kiểm tra |
| --- | --- | --- |
| IAM | Người dùng có quyền thực hiện thao tác ở compartment này không? | Người dùng, nhóm, policy và compartment đang chọn |
| Service limit | Oracle cấp bao nhiêu tài nguyên cho tenancy trong phạm vi này? | Limits, Quotas and Usage, đúng dịch vụ và vùng |
| Compartment quota | Quản trị viên cho phép compartment dùng bao nhiêu? | Quota policy áp dụng cho compartment |
| Capacity | Hạ tầng hiện còn chỗ cấp tài nguyên mong muốn không? | Thông báo lỗi cấp phát và phạm vi triển khai |
| Ưu đãi | Mức sử dụng đó có thuộc phần miễn phí không? | Điều kiện Free Tier và mức sử dụng tổng |

Oracle đặt service limits; quản trị viên đặt compartment quotas. Còn quota không có nghĩa tài nguyên được miễn phí. Tham khảo [Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm) và [Overview of Compartment Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas.htm). Capacity là lớp khả dụng hạ tầng riêng, được mô tả trong [Overview of the Compute Service](https://docs.oracle.com/en-us/iaas/Content/Compute/Concepts/computeoverview.htm).

Ví dụ: một bài lab cần thêm VM nhưng bị từ chối. Trước khi sửa cấu hình, ghi nguyên thông báo lỗi và thời điểm xảy ra. Nếu lỗi thuộc quyền truy cập, xem lại IAM; nếu thuộc hạn mức, kiểm tra usage và quota; nếu là thiếu capacity, không tự động chuyển sang shape lớn hơn rồi giả định nó vẫn miễn phí.

## 6. Khi trial kết thúc, điều gì xảy ra?

Nếu không nâng cấp, tài khoản vẫn hoạt động và có thể tiếp tục dùng phần Always Free đủ điều kiện. Tài nguyên trả phí tạo bằng credit trial sẽ bị Oracle thu hồi nếu tài khoản không được nâng cấp. Đặc biệt, tài liệu hiện cảnh báo A1 vượt phần dành cho tenancy Always Free có thể khiến toàn bộ các instance A1 hiện có bị vô hiệu hóa rồi xóa sau 30 ngày nếu không nâng cấp. Xem [When Your Trial Period Ends](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm).

Không dùng thời gian xử lý sau trial như lịch sao lưu. Hãy chọn một trong ba cách cho từng tài nguyên **trước khi** ưu đãi kết thúc:

| Quyết định | Công việc cần hoàn tất |
| --- | --- |
| Giữ trong phạm vi Always Free | Đối chiếu tổng mức dùng và điều chỉnh cấu hình đủ sớm |
| Kết thúc thí nghiệm | Xuất dữ liệu, giữ mô tả cấu hình cần thiết, xóa tài nguyên không cần |
| Tiếp tục bằng PAYG | Ước tính chi phí, rà tài nguyên hiện có và hoàn tất nâng cấp có chủ đích |

Một kế hoạch học tập mẫu có thể dành buổi đầu để thiết lập tài khoản, các buổi tiếp theo cho IAM và mạng, rồi mới thử dịch vụ dùng credit. Đặt một mốc tự kiểm tra vài ngày trước hạn trial. Mốc này do bạn tự chọn để có thời gian xử lý; nó không phải thời gian gia hạn do Oracle bảo đảm.

Sau khi giảm cấu hình, hãy kiểm tra tổng tài nguyên còn lại. Chỉ xóa một máy trong khi vẫn giữ tài nguyên phụ thuộc có thể khiến danh sách lab chưa phản ánh đúng những gì đang được cấp.

## 7. Nâng cấp PAYG khi có nhu cầu rõ ràng

PAYG phù hợp khi bài thực hành cần vượt phần Always Free, cần dịch vụ ngoài phạm vi ưu đãi hoặc cần duy trì tài nguyên trả phí sau trial. Nâng cấp là bước chấp nhận cơ chế thanh toán cho mức sử dụng tương ứng; không nên thực hiện chỉ để thử xem một lỗi cấp phát có hết hay không.

Oracle cung cấp chức năng nâng cấp trong Console; với luồng được hỗ trợ, có thể tìm **Billing & Cost Management → Upgrade and Manage Payment**. Quyền nâng cấp và quản lý thẻ thuộc nhóm Administrators. Luồng cụ thể có thể phụ thuộc quốc gia và tài khoản; xem [Managing Account Upgrades and Payment Method](https://docs.oracle.com/en-us/iaas/Content/Billing/Tasks/changingpaymentmethod.htm).

Trước khi xác nhận:

1. Kiểm kê mọi tài nguyên hiện có, gồm những tài nguyên được tạo thử bằng credit.
2. Chốt cấu hình cần giữ, thời gian chạy và người chịu trách nhiệm dọn lab.
3. Lập dự toán bằng [OCI Cost Estimator](https://www.oracle.com/cloud/costestimator.html), đọc đơn vị tính của từng hạng mục.
4. Kiểm tra điều khoản, phương thức thanh toán và các khoản thuế hoặc tiền tệ áp dụng.
5. Thiết lập theo dõi chi phí và giới hạn tài nguyên phù hợp.

Sau nâng cấp, đọc lại loại subscription và trạng thái ưu đãi trong Console. Không coi credit trial còn lại là lý do để bỏ qua việc kiểm tra tài nguyên đang chạy. Phần đủ điều kiện Always Free vẫn có thể được miễn phí; phần ngoài điều kiện phải được đánh giá theo cơ chế trả phí.

## 8. Thiết lập cách kiểm soát chi phí cho lab

### 8.1. Dùng compartment để lập phạm vi thực hành

Đề xuất một compartment lab riêng, chẳng hạn `oci-learning`, giúp bạn có một phạm vi cụ thể khi cấp quyền, liệt kê tài nguyên và theo dõi chi phí. Việc tạo compartment không tự đặt ngân sách hoặc ngăn tài nguyên trả phí.

Với mỗi lab, ghi tối thiểu tên tài nguyên, dịch vụ, region, compartment, mục đích và thời điểm dự kiến xóa. Khi học tự động hóa, giữ cấu hình triển khai để có thể dựng lại môi trường, thay vì giữ tài nguyên chạy vô thời hạn chỉ vì sợ mất cấu hình.

### 8.2. Budget gửi cảnh báo

OCI Budget là **ngưỡng mềm** để theo dõi chi tiêu thực tế hoặc dự báo và gửi cảnh báo. Budget không tự chặn sử dụng khi đạt ngưỡng. Oracle hiện đánh giá cảnh báo theo chu kỳ 24 giờ; đừng xem email ngân sách là cơ chế ngắt chi phí tức thời. Tham khảo [Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm).

Ví dụ kế hoạch cá nhân: nếu chấp nhận tối đa 10 USD cho một lab trả phí trong tháng, bạn có thể đặt cảnh báo ở 50%, 80% và 100%, rồi tự quy định ngừng thí nghiệm khi nhận cảnh báo đầu tiên ngoài dự kiến. Các mức này là ví dụ tổ chức công việc, không phải cam kết rằng hóa đơn sẽ dừng ở 10 USD.

### 8.3. Quota giới hạn lượng tài nguyên

Compartment quota dùng để hạn chế lượng tài nguyên của các dịch vụ được hỗ trợ, ví dụ giới hạn số core được cấp cho lab. Có thể tạo quota policy từ chức năng **Limits, Quotas and Usage** theo [tài liệu Compartment Quotas](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/resourcequotas.htm).

Quota kiểm soát đơn vị tài nguyên được chỉ định, không phải trần tiền áp dụng cho mọi dịch vụ. Khi thiết kế giới hạn, đối chiếu cả tài nguyên phụ thuộc và quyền sửa quota; nếu người thực hành có thể tự tăng giới hạn, giới hạn đó không còn là ràng buộc độc lập với họ.

### 8.4. Cost Analysis giúp tìm nguồn chi phí

Dùng **Cost Analysis** để xem theo thời gian, lọc compartment hoặc region và nhóm theo dịch vụ. Khi cần xác định hạng mục đang tiêu thụ, tiếp tục xem mô tả sản phẩm hoặc SKU. Tài liệu Oracle hiện lưu ý dữ liệu có thể mất đến **48 giờ** để xuất hiện; số 0 ngay sau khi tạo tài nguyên chưa chứng minh không có chi phí. Xem [Cost Analysis](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm).

Thói quen thực hành hữu ích là ghi dự toán trước khi chạy, kiểm kê sau buổi học rồi đối chiếu báo cáo khi dữ liệu được cập nhật. Nếu có hạng mục ngoài kế hoạch, tìm tài nguyên tương ứng trước khi tiếp tục tạo thêm.

## 9. Dọn lab theo thành phần

**Stop** và **Terminate** có mục đích khác nhau. Billing khi dừng VM phụ thuộc shape; tắt hệ điều hành bên trong VM không đồng nghĩa đã dừng tính phí Compute. Xem [Resource Billing for Stopped Instances](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/resource-billing-stopped-instances.htm).

Khi terminate instance, OCI có lựa chọn giữ boot volume. Volume giữ lại cần được theo dõi riêng; terminate không phải thao tác có thể hoàn tác. Xem [Compute FAQ](https://www.oracle.com/cloud/compute/faq/).

Quy trình kết thúc lab nên đi theo danh sách đã lập:

1. Xuất dữ liệu cần giữ và xác minh bản xuất trước khi xóa.
2. Xóa hoặc dừng tài nguyên theo đúng mục tiêu của buổi học và chính sách billing tương ứng.
3. Kiểm tra boot volume, block volume, bản sao lưu, bucket, database và các thành phần mạng đã tạo.
4. Giữ lại những thành phần có lý do cụ thể, người chịu trách nhiệm và ngày rà soát tiếp theo.
5. Kiểm tra lại theo từng region đã dùng; sau đó đối chiếu Cost Analysis khi dữ liệu cập nhật.

Ví dụ: nếu chỉ học cách tạo rồi kết nối VM, kết quả cần giữ có thể là ghi chép và cấu hình triển khai. Không nhất thiết phải giữ một máy đang chạy để chứng minh đã hoàn thành bài.

## 10. Xử lý các vướng mắc thường gặp

| Tình huống | Cách xử lý trong phạm vi bài học |
| --- | --- |
| Xác minh thẻ không hoàn tất | Kiểm tra thông tin đã nhập và loại thẻ được hỗ trợ; hỏi ngân hàng về trạng thái xác minh nếu cần |
| Có khoản giữ tiền nhưng chưa vào được Console | Phân biệt bước xác minh thanh toán với bước cấp tenancy; lưu thời điểm và thông báo lỗi đã loại bỏ thông tin nhạy cảm |
| Không tạo được VM mong muốn | Phân loại lỗi IAM, service limit, quota hoặc capacity trước khi thay cấu hình |
| Trial hết và tài nguyên trả phí không còn | Đối chiếu loại tài nguyên với chính sách kết thúc trial; dùng bản xuất hoặc cấu hình đã lưu để tiếp tục kế hoạch học |
| Có chi phí ngoài dự toán | Dừng tạo thêm tài nguyên, xác định dịch vụ và region liên quan, rồi kiểm kê thành phần phụ thuộc |
| Mất quyền truy cập MFA | Dùng phương án khôi phục đã chuẩn bị hoặc kênh hỗ trợ chính thức |

Đối với lỗi đăng ký, đăng nhập hoặc MFA, FAQ chỉ dẫn dùng kênh Chat của Oracle Cloud Support. Free Tier không bao gồm SLA; mức hỗ trợ dành cho tài khoản chỉ dùng Always Free có giới hạn. Xem [FAQ Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/faq/). Hãy xem lab miễn phí là môi trường có thể cần dựng lại và chuẩn bị dữ liệu tương ứng.

## 11. Thực hành: lập hồ sơ tài khoản và kế hoạch lab đầu tiên

Bài thực hành này chưa yêu cầu tạo dịch vụ trả phí hoặc nâng cấp PAYG. Kết quả cần có là một hồ sơ môi trường và một quyết định triển khai có căn cứ.

### Bước 1 — Ghi nhận môi trường

Điền các giá trị thực tế từ Console vào ghi chép cá nhân:

```text
Tên tenancy:
Home region:
Region đang chọn:
Identity domain đăng nhập:
Loại subscription:
Credit còn lại, nếu có:
Ngày giờ kết thúc trial, nếu có:
MFA đã đăng ký và đã thử đăng nhập lại:
Người quản lý phương thức thanh toán:
```

Không đưa mật khẩu, số thẻ, OTP, recovery code hoặc khóa riêng vào biểu mẫu này.

### Bước 2 — Lập danh sách tài nguyên dự kiến

Ví dụ dưới đây là khung lập kế hoạch cho một ứng dụng Java nhỏ, chưa khẳng định các lựa chọn sẽ được miễn phí:

| Thành phần | Điều cần xác minh trước khi tạo | Phương án kết thúc |
| --- | --- | --- |
| VM ứng dụng | Shape, kiến trúc CPU, tổng core/RAM, home region | Giữ cấu hình triển khai; xóa khi kết thúc thử nghiệm |
| Boot volume | Dung lượng, cấu hình hiệu năng, tổng volume hiện có | Quyết định rõ có cần giữ sau khi xóa VM |
| Object Storage nếu cần | Dung lượng, thao tác và truyền dữ liệu của lab | Xóa dữ liệu thử theo kế hoạch |
| Cơ sở dữ liệu nếu cần | Lựa chọn Always Free hoặc phần dùng credit/PAYG | Xuất dữ liệu và xác minh bản xuất |

Nếu chưa xác định được điều kiện miễn phí hoặc giá của một thành phần, đánh dấu **chưa triển khai**. Hoàn tất việc đọc cấu hình và đơn vị tính trước khi đưa nó vào kế hoạch.

### Bước 3 — Đặt giới hạn và lịch kiểm tra

Ghi ngân sách cá nhân chấp nhận được, phạm vi compartment, những dịch vụ được phép dùng và thời điểm dọn lab. Nếu đang trial, thêm mốc rà soát trước ngày hết hạn. Với lab trả phí sau này, bổ sung budget và quota phù hợp rồi xác minh quyền quản lý các thiết lập đó.

### Điều kiện hoàn thành

- Đăng nhập lại thành công, xác định đúng tenancy và home region.
- Chỉ rõ tài khoản đang ở trạng thái trial, sau trial hay PAYG.
- Phân loại từng thành phần lab theo Always Free, credit trial hoặc trả phí dự kiến.
- Biết nơi xem hạn mức, quota và dữ liệu chi phí.
- Có lịch dọn tài nguyên, nơi giữ dữ liệu cần thiết và cách dựng lại môi trường.

Khi có đủ các thông tin này, bạn đã sẵn sàng bắt đầu các bài thực hành hạ tầng OCI với phạm vi tài nguyên và trách nhiệm chi phí rõ ràng.
