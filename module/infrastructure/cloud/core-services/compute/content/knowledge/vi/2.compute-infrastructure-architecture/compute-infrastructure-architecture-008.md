# Mô hình thuê riêng phần cứng và yêu cầu giấy phép phần mềm

## 1. Bài toán thuê riêng phần cứng trong cloud

Phần lớn nền tảng cloud cung cấp năng lực tính toán trên hạ tầng dùng chung. Nhiều khách hàng có thể chạy máy ảo trên cùng một cụm máy chủ vật lý, trong khi nhà cung cấp chịu trách nhiệm phân vùng tài nguyên và cô lập các workload. Mô hình dùng chung thường linh hoạt và có hiệu quả chi phí tốt. Tuy nhiên, một số workload cần mức cô lập phần cứng cao hơn, khả năng kiểm soát vị trí đặt máy ảo, hiệu năng ổn định hoặc bằng chứng rõ ràng về máy chủ đang chạy phần mềm.

Đó là lúc các mô hình **dedicated instance**, **dedicated host**, **sole-tenant node** hoặc **bare metal** được xem xét. Chúng dành riêng một phần hoặc toàn bộ máy chủ vật lý cho một khách hàng, tùy cách triển khai của nhà cung cấp. Quyền sử dụng phần cứng riêng có thể giúp đáp ứng yêu cầu cách ly, kiểm toán, tuân thủ hoặc điều kiện giấy phép phần mềm doanh nghiệp.

Thuê riêng phần cứng không tự động giải quyết mọi yêu cầu. Mỗi mô hình có mức độ kiểm soát khác nhau đối với máy chủ, CPU, hypervisor và vị trí đặt VM. Đồng thời, giấy phép phần mềm có thể được tính theo người dùng, thiết bị, instance, vCPU, lõi vật lý, socket, máy chủ hoặc toàn bộ cụm. Nếu chọn sai mô hình tenancy hoặc hiểu sai đơn vị cấp phép, tổ chức có thể trả chi phí phần cứng cao mà vẫn không đáp ứng hợp đồng phần mềm.

Trong bài này, người học sẽ:

- Phân biệt hạ tầng dùng chung, dedicated instance, dedicated host, sole-tenant và bare metal.
- Hiểu mức độ cô lập, quyền kiểm soát và trách nhiệm vận hành của từng mô hình.
- Nhận diện các cách tính giấy phép phần mềm và mối liên hệ với CPU, host, VM, người dùng.
- Thiết kế placement, mở rộng, tính sẵn sàng và khôi phục sao cho phù hợp với điều khoản cấp phép.
- Tính tổng chi phí sở hữu và xây dựng bằng chứng phục vụ kiểm toán giấy phép.

## 2. Các khái niệm nền tảng

### 2.1. Máy chủ vật lý, hypervisor, VM và vCPU

Máy chủ vật lý (physical host) là máy tính thực tế có CPU, bộ nhớ, thiết bị mạng và thiết bị lưu trữ. Trong môi trường ảo hóa, hypervisor phân chia tài nguyên máy chủ thành nhiều máy ảo. Mỗi VM nhìn thấy một cấu hình phần cứng ảo và chạy hệ điều hành khách riêng.

Một số thuật ngữ cần phân biệt:

- **Socket:** vị trí gắn một CPU vật lý trên bo mạch chủ. Một máy chủ có thể có một hoặc nhiều socket.
- **Core:** lõi xử lý vật lý bên trong CPU. Một CPU có nhiều core.
- **Hardware thread:** luồng thực thi được CPU hỗ trợ bằng công nghệ như simultaneous multithreading (SMT). Hai hardware thread trên cùng một core không tương đương hai core vật lý.
- **vCPU:** đơn vị CPU ảo được nền tảng cung cấp cho VM hoặc container. Cách ánh xạ vCPU sang core hoặc hardware thread tùy nhà cung cấp và loại instance.
- **NUMA:** kiến trúc trong đó CPU truy cập một số vùng bộ nhớ gần nó nhanh hơn các vùng bộ nhớ khác. Workload lớn hoặc nhạy độ trễ có thể bị ảnh hưởng bởi cách phân bố CPU và bộ nhớ qua các NUMA node.

Không nên mặc định một vCPU luôn bằng một core vật lý. Trong một số nền tảng, vCPU tương ứng với một hardware thread; trong nền tảng khác, cách biểu diễn và phân bổ có thể khác. Tương tự, số core hiển thị trong hệ điều hành khách không nhất thiết cho biết số core vật lý phải dùng để tính giấy phép. Cần dùng định nghĩa trong tài liệu nhà cung cấp cloud và hợp đồng của nhà cung cấp phần mềm.

### 2.2. Tenancy và cô lập phần cứng

Tenancy mô tả cách tài nguyên vật lý được phân bổ giữa các khách hàng. Ở mô hình dùng chung, nhà cung cấp có thể đặt VM của nhiều khách hàng trên cùng host, nhưng phải cô lập chúng bằng lớp ảo hóa và các cơ chế bảo mật liên quan. Ở mô hình dedicated, một máy chủ hoặc một phần hạ tầng vật lý được dành cho một khách hàng theo điều kiện dịch vụ.

**Cô lập phần cứng** có nghĩa là workload của khách hàng không chia sẻ máy chủ vật lý với workload của khách hàng khác theo phạm vi cam kết. Điều đó khác với việc chỉ có một VM trên một host tại một thời điểm do tình cờ. Cần đọc chính xác định nghĩa tenancy trong dịch vụ cloud: phạm vi dành riêng có thể là instance, host, node group, rack hoặc một vùng tài nguyên cụ thể.

Dedicated hardware cũng không đồng nghĩa với máy chủ chỉ có thể chạy một workload. Khách hàng có thể chạy nhiều VM của chính mình trên một dedicated host. Họ cũng có thể cài hypervisor riêng trên bare-metal server nếu dịch vụ và hợp đồng cho phép.

## 3. Các mô hình thuê riêng phần cứng

### 3.1. Hạ tầng dùng chung (shared tenancy)

Ở shared tenancy, nhiều khách hàng dùng chung cụm máy chủ vật lý. Hypervisor và lớp quản lý cloud chịu trách nhiệm phân chia CPU, bộ nhớ, mạng và lưu trữ. Khách hàng thường chỉ quản lý VM hoặc dịch vụ compute được cấp, không biết chính xác VM đang nằm trên host vật lý nào.

Ưu điểm của shared tenancy là dễ cấp phát, linh hoạt khi tăng giảm số lượng instance và thường có chi phí khởi đầu thấp. Nhà cung cấp có thể tận dụng tài nguyên trên toàn cụm để cải thiện hiệu suất sử dụng. Đây thường là lựa chọn phù hợp cho ứng dụng web, môi trường phát triển, dịch vụ nội bộ và nhiều workload thông thường.

Giới hạn là khách hàng ít quyền kiểm soát host, có thể không biết host ID hoặc cấu hình vật lý cụ thể, và có thể chịu ảnh hưởng từ đặc tính chia sẻ tài nguyên tùy loại instance và chính sách của nhà cung cấp. Shared tenancy có thể không đáp ứng điều khoản phần mềm yêu cầu cài đặt trên máy chủ được chỉ định hoặc yêu cầu chứng minh phạm vi phần cứng.

### 3.2. Dedicated instance

Dedicated instance là instance được chạy trên phần cứng dành riêng cho một khách hàng theo định nghĩa của nhà cung cấp. Khách hàng có thể nhận được cam kết cô lập host ở cấp instance, nhưng không nhất thiết được chọn host cụ thể, xem đầy đủ thông tin socket/core hoặc kiểm soát vị trí của các instance khác cùng tài khoản.

Đặc điểm quan trọng là **mức cô lập có thể cao hơn nhưng quyền kiểm soát host vẫn hạn chế**. Nhà cung cấp có thể tự quyết định đặt instance lên máy chủ nào và thay đổi vị trí khi bảo trì. Một số dịch vụ có thể hỗ trợ affinity hoặc khả năng xem thông tin phần cứng; dịch vụ khác thì không. Không nên suy ra các quyền đó chỉ từ tên gọi dedicated instance.

Dedicated instance có thể phù hợp khi yêu cầu chính là cô lập với khách hàng khác. Nếu mục tiêu là kiểm soát số core vật lý, gắn giấy phép theo host, theo dõi host ID hoặc ràng buộc phần mềm vào một máy chủ cụ thể, cần xác minh rằng dịch vụ cung cấp đủ thông tin và quyền quản lý cần thiết.

### 3.3. Dedicated host

Dedicated host là máy chủ vật lý được dành riêng cho một khách hàng. Khách hàng thường có khả năng đặt nhiều VM của mình lên host đó và có thể được cung cấp thông tin như host ID, họ máy, socket, số core hoặc dung lượng còn lại. Tùy dịch vụ, khách hàng có thể chọn kích thước host, nhóm instance tương thích, affinity, anti-affinity hoặc placement control.

Dedicated host thường hữu ích khi giấy phép phần mềm được tính theo số core vật lý, socket hoặc toàn bộ máy chủ. Khi biết chính xác host nào đang chạy VM và có thể kiểm soát placement, tổ chức dễ xây dựng bản đồ cấp phép và bằng chứng kiểm toán hơn. Dedicated host cũng có thể đáp ứng yêu cầu không chia sẻ máy chủ vật lý với khách hàng khác.

Đổi lại, khách hàng có thể phải trả phí theo host hoặc theo thời gian host được cấp, kể cả khi chỉ sử dụng một phần CPU và bộ nhớ. Khả năng mở rộng phụ thuộc vào số host có sẵn, quota, thời gian cấp host và giới hạn của họ máy. Cần tính chi phí tài nguyên nhàn rỗi, dự phòng HA và host thay thế khi bảo trì.

### 3.4. Sole-tenant node hoặc node chuyên biệt

Một số nhà cung cấp dùng khái niệm sole-tenant node để chỉ node vật lý chỉ dành cho một khách hàng trong môi trường điều phối VM. Khách hàng có thể triển khai nhiều VM trên node, sử dụng chính sách node affinity hoặc node group để điều khiển placement. Tên gọi, mức hiển thị phần cứng và cơ chế thanh toán khác nhau giữa các nhà cung cấp.

Sole-tenant node thường phù hợp với workload cần ranh giới vật lý riêng nhưng vẫn muốn dùng mô hình VM và công cụ quản lý cloud. Khi đánh giá, cần xác minh liệu node có tương đương dedicated host theo hợp đồng phần mềm hay không. Một số hợp đồng cấp phép định nghĩa host, server, processor hoặc hardware partition theo cách riêng; tên dịch vụ cloud không tự quyết định cách diễn giải hợp đồng.

### 3.5. Bare metal

Bare metal cung cấp máy chủ vật lý trực tiếp cho khách hàng, thường không có hypervisor do nhà cung cấp quản lý ở giữa giao diện sử dụng. Khách hàng có thể cài hệ điều hành, hypervisor hoặc nền tảng container của riêng mình nếu dịch vụ cho phép. Mô hình này mang lại quyền kiểm soát sâu hơn đối với CPU, bộ nhớ, thiết bị mạng và một số đặc tính I/O.

Bare metal phù hợp với workload cần hiệu năng ổn định, truy cập phần cứng đặc thù, license hoặc phần mềm yêu cầu môi trường máy chủ riêng, hệ thống cơ sở dữ liệu lớn, HPC hoặc nền tảng ảo hóa do khách hàng tự quản lý. Tuy nhiên, quyền kiểm soát cao đi kèm trách nhiệm quản trị hệ điều hành, hypervisor, bản vá, cấu hình bảo mật, giám sát và khôi phục.

Bare metal không tự động có nghĩa là không thể ảo hóa. Khách hàng có thể cài hypervisor của riêng mình, sau đó chạy VM trên máy chủ vật lý. Khi đó, phải xác định rõ hợp đồng phần mềm cho phép cấp phép ở tầng bare metal, hypervisor, host hay từng VM.

### 3.6. Bảng so sánh các mô hình

| Tiêu chí | Shared tenancy | Dedicated instance | Dedicated host / sole-tenant | Bare metal |
|---|---|---|---|---|
| Phạm vi dành riêng | Host dùng chung giữa khách hàng | Instance được cam kết chạy trên phần cứng riêng theo dịch vụ | Máy chủ/node vật lý dành riêng cho một khách hàng | Máy chủ vật lý cấp trực tiếp cho khách hàng |
| Quyền xem host vật lý | Thường rất hạn chế | Tùy dịch vụ, thường hạn chế hơn dedicated host | Thường có host ID và thông tin phần cứng | Thường có thông tin máy chủ rõ hơn |
| Kiểm soát placement | Thấp | Thường thấp đến trung bình | Có thể có affinity, anti-affinity hoặc placement control | Khách hàng kiểm soát hệ điều hành/hypervisor và workload trên máy được cấp |
| Quản trị hypervisor | Nhà cung cấp | Nhà cung cấp | Nhà cung cấp thường quản lý hypervisor | Có thể do khách hàng cài/quản lý hoặc theo dịch vụ |
| Khả năng đáp ứng license theo host | Phải xác minh; thường khó chứng minh | Phải xác minh phạm vi host và quyền kiểm soát | Thường thuận lợi hơn nếu hợp đồng và metadata phù hợp | Có thể thuận lợi nếu điều khoản chấp nhận cấu trúc máy chủ |
| Hiệu quả sử dụng tài nguyên | Cao nhờ dùng chung | Có thể có phần tài nguyên không sử dụng hết | Khách hàng chịu chi phí công suất host đã cấp | Khách hàng chịu trách nhiệm tận dụng công suất máy vật lý |
| Công sức vận hành | Thấp hơn ở tầng phần cứng | Thấp đến trung bình | Trung bình; thêm quản lý host và placement | Cao hơn nếu tự quản lý OS/hypervisor |

Tên gọi và cam kết kỹ thuật không đồng nhất giữa các nhà cung cấp. Hãy đối chiếu tài liệu dịch vụ, hợp đồng cloud và điều khoản của nhà cung cấp phần mềm trước khi quyết định.

## 4. Các mô hình cấp phép phần mềm thường gặp

### 4.1. Cấp phép theo người dùng hoặc thiết bị

Giấy phép có thể được tính theo số người dùng được phép truy cập hoặc số thiết bị sử dụng phần mềm. Cách tính này thường gặp ở một số ứng dụng doanh nghiệp, hệ thống truy cập, công cụ quản trị và sản phẩm máy khách/máy chủ.

Khi triển khai trên cloud, cần xác định người dùng được tính là người dùng được đặt tên (named user), người dùng đồng thời (concurrent user), người dùng truy cập gián tiếp hay tài khoản dịch vụ. Với cấp phép theo thiết bị, cần quản lý thiết bị vật lý, thiết bị ảo hoặc endpoint theo định nghĩa hợp đồng. Việc đưa ứng dụng lên VM không làm biến mất nghĩa vụ cấp phép cho người dùng hoặc thiết bị.

### 4.2. Cấp phép theo instance hoặc VM

Một số phần mềm tính giấy phép theo số instance, máy chủ ảo hoặc môi trường cài đặt. Điều khoản có thể quy định số lượng VM tối đa, cấu hình tối thiểu, quyền chạy nhiều bản sao hoặc giới hạn môi trường phát triển và kiểm thử.

Mô hình này đòi hỏi kiểm soát số VM được tạo, clone, snapshot và khởi chạy. Một VM tạm thời phục vụ migration, test hoặc autoscaling có thể vẫn được tính là một instance được cấp phép, tùy điều khoản. Không nên cho rằng VM tắt hoặc chỉ chạy trong thời gian ngắn thì mặc nhiên không cần license.

### 4.3. Cấp phép theo vCPU hoặc core được phân bổ cho VM

Với mô hình cấp phép theo core ảo, số vCPU được gán cho VM có thể là cơ sở tính số license. Hợp đồng có thể quy định số core tối thiểu cho mỗi VM, cách làm tròn, giới hạn số vCPU, loại CPU được hỗ trợ hoặc quyền di chuyển VM giữa các host.

Khi sử dụng autoscaling, việc tạo thêm VM hoặc tăng vCPU có thể làm tăng nhu cầu license. Hãy đồng bộ quy trình cấp phát compute với quy trình kiểm tra entitlement. Cần lưu lại cấu hình vCPU, thời điểm thay đổi, phiên bản phần mềm và lịch sử placement.

### 4.4. Cấp phép theo core vật lý, socket hoặc processor

Một số sản phẩm doanh nghiệp tính license dựa trên số core vật lý, socket hoặc processor của máy chủ. Trong trường hợp này, việc chỉ nhìn số vCPU bên trong VM có thể dẫn đến tính thiếu giấy phép. Hợp đồng có thể yêu cầu cấp phép cho toàn bộ core trên host, các core có khả năng chạy workload, hoặc một phần core theo quy tắc cụ thể.

Đây là trường hợp dedicated host hoặc bare metal có thể quan trọng. Khách hàng cần biết host vật lý có bao nhiêu socket/core, host nào được phép chạy phần mềm và liệu VM có thể được di chuyển sang host khác hay không. Nếu license gắn với host, một thao tác live migration, thay host khi bảo trì hoặc mở rộng cluster có thể thay đổi phạm vi cấp phép.

Không có quy tắc chung rằng mọi license theo core đều phải cấp phép toàn bộ core vật lý. Cũng không có quy tắc chung rằng chỉ cần cấp phép số vCPU được gán cho VM. Cách tính phụ thuộc hợp đồng, phiên bản, edition, chương trình cấp phép và chính sách cloud của nhà cung cấp phần mềm.

### 4.5. Cấp phép theo host, cluster hoặc dung lượng

Một số sản phẩm được cấp phép theo máy chủ, theo cụm, theo dung lượng lưu trữ, theo dung lượng dữ liệu được quản lý hoặc theo một đơn vị năng lực khác. Có hợp đồng yêu cầu cấp phép toàn bộ cluster nếu phần mềm có thể chạy trên mọi node trong cluster. Hợp đồng khác chỉ tính các node thực sự cài đặt hoặc được chỉ định chạy phần mềm.

Phải phân biệt **nơi phần mềm được cài**, **nơi phần mềm có thể chạy**, và **nơi hợp đồng yêu cầu cấp phép**. Ba phạm vi này có thể khác nhau. Một cluster có 10 node nhưng chỉ 2 node chạy database chưa chắc chỉ cần license cho 2 node; điều khoản có thể xét đến khả năng failover hoặc quyền di chuyển workload.

### 4.6. Giấy phép bao gồm trong dịch vụ và BYOL

Có hai cách mua phổ biến khi dùng cloud:

- **License-included:** phí dịch vụ compute hoặc dịch vụ quản lý đã bao gồm quyền sử dụng một phần mềm nhất định. Nhà cung cấp cloud thường quản lý việc cấp phép trong phạm vi dịch vụ được nêu.
- **Bring Your Own License (BYOL):** khách hàng mang giấy phép đã mua hoặc ký hợp đồng riêng vào môi trường cloud. Khách hàng phải xác minh quyền triển khai trên cloud, điều kiện về host, region, virtualization, mobility và kiểm toán.

BYOL không có nghĩa giấy phép mua cho máy chủ tại chỗ luôn được phép chuyển lên cloud. Một số chương trình cấp phép cho phép di chuyển hoặc tái phân bổ trong điều kiện cụ thể; một số chương trình giới hạn nhà cung cấp, phần cứng hoặc thời gian chuyển đổi. Cần có xác nhận bằng văn bản từ nhà cung cấp phần mềm hoặc đối tác cấp phép có thẩm quyền.

### 4.7. Các quyền và ngoại lệ cần kiểm tra

Hợp đồng có thể quy định riêng cho:

- Quyền di chuyển license giữa máy chủ (license mobility) và thời gian tối thiểu giữa hai lần chuyển.
- Quyền chạy máy chủ dự phòng thụ động, failover node hoặc disaster recovery site.
- Môi trường phát triển, kiểm thử, staging, sandbox và đào tạo.
- Quyền chạy nhiều phiên bản, nhiều container hoặc nhiều bản sao phần mềm.
- Quyền dùng phần mềm trong vùng cloud, quốc gia hoặc nhà cung cấp cụ thể.
- Quyền sử dụng trong thời gian bảo trì, thay host hoặc chuyển vùng.
- Điều kiện gia hạn, bảo trì phần mềm, subscription, support và phiên bản được phép chạy.

Không được tự suy luận rằng máy chủ dự phòng, VM dừng, snapshot, image template hoặc môi trường DR được miễn license. Chỉ áp dụng ngoại lệ khi hợp đồng nêu rõ điều kiện và phạm vi.

## 5. Ghép mô hình phần cứng với mô hình cấp phép

### 5.1. Ma trận quyết định ban đầu

| Nhu cầu hoặc điều khoản | Mô hình cần đánh giá | Bằng chứng cần xác minh |
|---|---|---|
| Chỉ cần cô lập với khách hàng khác | Dedicated instance hoặc dedicated host | Cam kết tenancy, phạm vi host, quy tắc thay host |
| License tính theo core vật lý hoặc socket | Dedicated host, sole-tenant node hoặc bare metal | Số socket/core, host ID, CPU model, placement và quyền di chuyển |
| License tính theo VM/vCPU | Shared hoặc dedicated đều có thể phù hợp | Số vCPU, cấu hình tối thiểu, lịch sử VM và quyền chạy trên cloud |
| Cần tự quản lý hypervisor | Bare metal hoặc dịch vụ host cho phép cài hypervisor riêng | Quyền cài hypervisor, firmware, driver, thiết bị và hỗ trợ của nhà cung cấp |
| Cần hiệu năng I/O hoặc CPU ổn định | Dedicated host hoặc bare metal có cấu hình phù hợp | Benchmark, NUMA, loại CPU, băng thông mạng và lưu trữ |
| Cần kiểm soát host placement để kiểm toán | Dedicated host hoặc sole-tenant node có metadata | Host ID, API inventory, log placement và lịch sử migration |

Ma trận này chỉ dùng để sàng lọc. Điều khoản phần mềm và cam kết dịch vụ cloud mới là cơ sở kết luận. Ví dụ, dedicated host có thể cung cấp host ID nhưng chưa chắc đáp ứng định nghĩa “server được chỉ định” trong một hợp đồng cụ thể.

### 5.2. Ví dụ về khác biệt giữa vCPU và core vật lý

Giả sử một hệ thống có 2 dedicated host, mỗi host có 2 socket và 16 core vật lý trên mỗi socket. Tổng cộng hệ thống có 64 core vật lý. Trên các host này, đội ngũ chạy 4 VM, mỗi VM được gán 8 vCPU, tổng cộng 32 vCPU.

Nếu hợp đồng giả định trong ví dụ yêu cầu cấp phép theo toàn bộ core vật lý của host nơi phần mềm có thể chạy, cơ sở tính có thể là 64 core. Nếu hợp đồng khác cho phép cấp phép theo số vCPU được gán cho từng VM, cơ sở tính có thể là 32 vCPU, sau khi áp dụng các mức tối thiểu và quy tắc làm tròn của hợp đồng. Hai cách tính tạo ra kết quả khác nhau dù ứng dụng và cấu hình VM không đổi.

Đây chỉ là ví dụ minh họa để phân biệt đơn vị tính. Không dùng các con số này để kết luận nghĩa vụ cấp phép của một sản phẩm cụ thể. Phải đọc đúng điều khoản áp dụng cho sản phẩm, phiên bản, edition, chương trình cấp phép và nền tảng cloud đang sử dụng.

### 5.3. Placement, affinity và anti-affinity

Placement quyết định VM được chạy trên host nào. Khi license gắn với host, cần kiểm soát việc placement để tránh phần mềm chạy trên host chưa được cấp phép.

- **Host affinity:** ràng buộc workload vào một host hoặc nhóm host được phép.
- **Host anti-affinity:** yêu cầu các workload được đặt trên các host khác nhau, thường để giảm rủi ro khi một host gặp lỗi.
- **Placement group/node group:** nhóm tài nguyên vật lý hoặc logic được dùng làm phạm vi triển khai và quản lý.
- **Live migration:** di chuyển VM đang chạy từ host này sang host khác. Đây là thao tác cần kiểm tra về quyền license, host đích và log kiểm toán.
- **Host maintenance/replacement:** nhà cung cấp thay host khi bảo trì hoặc lỗi phần cứng. Cần biết host mới có cùng thuộc tính, host ID và phạm vi license như cũ hay không.

Nếu hợp đồng chỉ cho phép chạy phần mềm trên một nhóm host được cấp phép, hãy cấu hình policy để workload không tự động chạy sang host khác. Đối với failover, xác định trước host dự phòng nào được phép nhận workload và license có bao phủ tình huống đó hay không.

### 5.4. Cluster và phạm vi cấp phép

Khi xây dựng cluster, xác định rõ node nào có thể chạy workload được cấp phép. Nếu scheduler có thể đặt VM trên bất kỳ node nào, phạm vi license có thể rộng hơn số node đang hoạt động. Có thể tách node pool cho phần mềm cần license riêng, giới hạn quyền triển khai và áp dụng label/taint hoặc chính sách tương đương.

Việc tách node pool phải đi kèm kiểm soát ở nhiều lớp: quyền IAM, policy của nền tảng điều phối, pipeline triển khai, quota và giám sát. Chỉ gắn nhãn cho node mà không ngăn scheduler hoặc người vận hành triển khai nhầm thì chưa đủ để bảo đảm tuân thủ.

## 6. Thiết kế kiến trúc có xét đến giấy phép

### 6.1. Xác định ranh giới workload được cấp phép

Phân loại phần mềm theo cách tính license và mức độ quan trọng. Ghi rõ workload nào cần dedicated hardware, workload nào có thể chạy shared tenancy, và workload nào dùng license-included. Tránh đặt tất cả ứng dụng lên dedicated host nếu chỉ một số thành phần có yêu cầu đặc biệt.

Một mô hình phân vùng thường gặp:

```text
Cloud account / project
|
+-- Shared compute pool
|   +-- Web/API không có ràng buộc host license
|   +-- Worker và môi trường phát triển phù hợp shared tenancy
|
+-- Licensed dedicated pool
|   +-- Host A: workload được cấp phép theo host/core
|   +-- Host B: host dự phòng hoặc workload cùng phạm vi license
|
+-- Bare-metal pool (nếu cần)
    +-- Workload cần kiểm soát phần cứng hoặc hypervisor riêng
```

Đây là cách tổ chức logic. Tên tài nguyên và cơ chế thực hiện phụ thuộc dịch vụ cloud. Ranh giới cần được thực thi bằng quyền truy cập, policy placement và quy trình phát hành.

### 6.2. Lập bản đồ license và inventory phần cứng

Mỗi phần mềm được cấp phép cần có bản ghi nối giữa hợp đồng và tài nguyên cloud. Tối thiểu nên lưu:

- Tên sản phẩm, phiên bản, edition, nhà cung cấp và mã hợp đồng/entitlement nội bộ.
- Metric cấp phép: user, device, VM, vCPU, physical core, socket, host, cluster hoặc đơn vị khác.
- Số lượng license đã mua, số lượng được phân bổ và số lượng còn lại.
- Host ID, loại máy, CPU model, số socket, số core vật lý và vùng triển khai khi các dữ liệu này có liên quan.
- VM ID, vCPU, bộ nhớ, phần mềm được cài, thời gian tạo/xóa và host placement.
- Quyền mobility, failover, DR, test và các giới hạn khác theo hợp đồng.
- Bằng chứng nguồn: hợp đồng, xác nhận của nhà cung cấp, báo cáo cloud inventory và log thay đổi.

Inventory cần có thời điểm ghi nhận và lịch sử thay đổi. Một báo cáo hiện tại không đủ giải thích VM đã chạy trên host nào vào tháng trước khi kiểm toán theo kỳ.

### 6.3. Quản lý vòng đời host và VM

Quy trình cấp phát cần bao gồm kiểm tra license trước khi tạo VM hoặc cài phần mềm. Khi mở rộng, pipeline hoặc cổng phê duyệt phải kiểm tra host đích và số lượng license còn khả dụng. Khi xóa VM, cần cập nhật inventory và chỉ thu hồi license theo điều kiện hợp đồng.

Với dedicated host, theo dõi các trạng thái: được cấp, sẵn sàng, đang sử dụng, bảo trì, lỗi, thay thế và ngừng cấp. Nếu nhà cung cấp thay host, cần lưu host ID cũ/mới, thời điểm, thông tin phần cứng và xác nhận cách xử lý license. Không giả định việc thay host vật lý là một thay đổi vô hình đối với phần mềm cấp phép theo host.

Đối với VM template, image và snapshot, kiểm tra phần mềm được cài sẵn và cách chúng được tính license khi clone hoặc khởi chạy. Một template không chạy có thể được xử lý khác một instance đang hoạt động, nhưng phải theo điều khoản cụ thể.

### 6.4. Bảo mật và kiểm soát truy cập

Dedicated hardware giúp giảm phạm vi chia sẻ vật lý, nhưng không thay thế các biện pháp bảo mật. Cần tiếp tục áp dụng:

- IAM theo nguyên tắc đặc quyền tối thiểu; chỉ nhóm được phép mới có quyền tạo, thay đổi hoặc xóa host và VM.
- Phân tách tài khoản quản trị cloud, quản trị hệ điều hành và quản trị phần mềm được cấp phép.
- Mã hóa dữ liệu khi truyền và khi lưu; quản lý khóa qua dịch vụ chuyên dụng.
- Secure boot, firmware/BIOS baseline và cập nhật bản vá theo khả năng của dịch vụ.
- Phân đoạn mạng, giới hạn ingress/egress và quản lý đường truy cập quản trị.
- Log hoạt động tạo host, thay host, migration, cài đặt, gỡ cài đặt và thay đổi quyền.
- Kiểm kê image, phần mềm và thư viện để tránh cài đặt ngoài phạm vi license.

Khi yêu cầu tuân thủ đòi hỏi chứng minh cô lập, hãy lưu tài liệu dịch vụ và cam kết của nhà cung cấp. Không dùng một nhãn “dedicated” trên console làm bằng chứng duy nhất cho yêu cầu pháp lý hoặc kiểm toán.

## 7. Tính sẵn sàng, mở rộng và khôi phục

### 7.1. Dự phòng host và vùng khả dụng

Một dedicated host là một điểm lỗi vật lý. Nếu workload cần tính sẵn sàng cao, cần có host thứ hai hoặc cơ chế khôi phục trên một host/vùng khác. Tuy nhiên, host dự phòng có thể phát sinh chi phí ngay cả khi nhàn rỗi và có thể cần license cho failover.

Thiết kế HA phải xem xét cả phần cứng và phần mềm:

- Phân bố VM qua các host khác nhau bằng anti-affinity khi phù hợp.
- Phân bố qua nhiều vùng khả dụng nếu dịch vụ, dữ liệu và yêu cầu license cho phép.
- Xác định host dự phòng được phép nhận workload và số lượng license cần thiết khi failover.
- Kiểm tra khả năng khởi tạo host mới trong thời gian mục tiêu; quota và tồn kho host có thể ảnh hưởng RTO.
- Kiểm thử chuyển workload, khôi phục dữ liệu và đưa host trở lại cụm.

Không nên đặt hai VM bản sao trên cùng một host rồi coi đó là HA. Cũng không nên chuyển VM sang host chưa được cấp phép chỉ để khôi phục nhanh nếu hợp đồng không cho phép.

### 7.2. Mở rộng năng lực

Với shared tenancy, tăng số instance thường có thể thực hiện nhanh khi quota còn đủ. Với dedicated host, mở rộng có thể cần cấp thêm host, kiểm tra họ máy tương thích, cấu hình network/storage và phân bổ license. Thời gian cấp host có thể dài hơn thời gian scale VM trên host hiện có.

Khi lập kế hoạch capacity, hãy tính:

- Số VM, vCPU, bộ nhớ và I/O cần ở tải trung bình, tải đỉnh.
- Công suất host còn trống sau khi dành headroom cho HA và bảo trì.
- Quy tắc phân bổ CPU, NUMA và giới hạn bộ nhớ của workload lớn.
- Số host cần thiết theo chính sách anti-affinity và vùng khả dụng.
- License cần mua thêm khi thêm host, tăng vCPU hoặc mở rộng số người dùng.
- Quota, thời gian cấp host và khả năng có sẵn của loại phần cứng mong muốn.

Autoscaling trên dedicated pool cần giới hạn rõ ràng. Nếu scheduler tự tạo VM trên bất kỳ host nào, có thể phát sinh chi phí license hoặc vi phạm phạm vi host đã được phê duyệt. Hãy gắn chính sách autoscaling với node pool/host group được cấp phép và thiết lập ngưỡng tối đa dựa trên cả công suất lẫn entitlement.

### 7.3. Disaster recovery và quyền sử dụng license

Thiết kế DR cần trả lời: phần mềm được phép chạy ở vùng dự phòng không; license có thể di chuyển sang host hoặc vùng đó không; thời gian chờ trước khi tái phân bổ là bao lâu; máy chủ dự phòng có thể chạy thụ động hay phải được cấp phép đầy đủ; và điều kiện nào áp dụng khi diễn tập DR.

Lập bản đồ license cho cả môi trường production và DR. Nếu có quyền failover đặc biệt, lưu văn bản điều khoản, phạm vi và cách chứng minh hệ thống chỉ dùng quyền đó trong điều kiện cho phép. Đặt lịch diễn tập để kiểm tra cả kỹ thuật lẫn quy trình cập nhật inventory.

## 8. Tính tổng chi phí sở hữu

Dedicated host thường có chi phí cao hơn shared tenancy trên mỗi đơn vị tài nguyên nếu công suất sử dụng thấp. Tuy nhiên, với phần mềm có license theo core vật lý hoặc host, dedicated hardware có thể giúp tổ chức kiểm soát phạm vi cấp phép và tránh cấp license cho một cụm lớn hơn mức cần thiết. Phải so sánh tổng chi phí thay vì chỉ so giá instance.

Các thành phần chi phí cần tính:

1. **Compute:** phí host, bare-metal server, VM, thời gian host được giữ, chi phí đặt trước hoặc cam kết sử dụng.
2. **License:** license mới, subscription, bảo trì, support, quyền mobility, license cho host dự phòng và môi trường DR.
3. **Tài nguyên phụ:** storage, snapshot, backup, image registry, load balancer và thiết bị mạng.
4. **Network:** truyền dữ liệu liên vùng, egress, kết nối riêng và chi phí bảo mật mạng.
5. **Vận hành:** quản lý host, vá lỗi, giám sát, kiểm toán, quản lý hợp đồng và xử lý sự cố.
6. **Công suất nhàn rỗi:** CPU/bộ nhớ không dùng hết trên host, năng lực dự phòng HA và tài nguyên giữ sẵn để mở rộng.

Một công thức so sánh khái quát:

```text
TCO trong kỳ =
    chi phí compute và host
  + chi phí license, subscription và support
  + chi phí storage, backup và network
  + chi phí vận hành và kiểm toán
  + chi phí công suất dự phòng/nhàn rỗi
```

Hãy xây dựng ít nhất ba kịch bản: tải bình thường, tải đỉnh và tình huống host hoặc vùng bị lỗi. So sánh shared tenancy, dedicated host và bare metal theo cùng một đơn vị công việc, ví dụ chi phí trên một giao dịch thành công hoặc một giờ xử lý dữ liệu.

### Ví dụ so sánh định tính

Một tổ chức chạy phần mềm cơ sở dữ liệu có điều khoản cấp phép theo core vật lý. Shared tenancy có thể rẻ về compute, nhưng nếu không thể xác định host và phạm vi core theo cách hợp đồng yêu cầu, mô hình đó có thể không phù hợp với BYOL. Dedicated host có chi phí host cao hơn nhưng cung cấp host ID và số core rõ ràng, giúp lập kế hoạch license. Bare metal có thể phù hợp nếu workload cần kiểm soát hypervisor hoặc I/O sâu, nhưng làm tăng trách nhiệm vận hành.

Trong khi đó, các API stateless, worker không có ràng buộc license host và môi trường phát triển có thể tiếp tục chạy trên shared tenancy. Tách riêng nhóm workload có yêu cầu license thường giúp tránh trả phí dedicated hardware cho toàn bộ hệ thống.

## 9. Quy trình lựa chọn và triển khai

### Bước 1: Thu thập điều khoản cấp phép

Thu thập hợp đồng, product use rights, license guide, phụ lục cloud, xác nhận BYOL và tài liệu liên quan đến phiên bản/edition đang sử dụng. Xác định metric, số lượng, phạm vi host/VM, quyền di chuyển, failover, DR và môi trường test. Nếu ngôn ngữ hợp đồng chưa rõ, yêu cầu nhà cung cấp phần mềm hoặc bộ phận pháp chế/mua sắm xác nhận bằng văn bản.

### Bước 2: Lập hồ sơ workload và yêu cầu phần cứng

Ghi lại CPU, bộ nhớ, network, storage, hiệu năng, tính sẵn sàng, vùng dữ liệu, yêu cầu cô lập và cách triển khai. Xác định workload cần bare metal, dedicated host hay chỉ cần dedicated instance. Tách yêu cầu bắt buộc khỏi sở thích vận hành.

### Bước 3: Đối chiếu metric license với thông tin cloud

Kiểm tra nhà cung cấp cloud có cung cấp đủ dữ liệu để tính license hay không: host ID, socket, core, CPU model, vCPU, placement history và thông tin thay host. Nếu thiếu dữ liệu bắt buộc, cần chọn dịch vụ khác hoặc có xác nhận chính thức về cách tính.

### Bước 4: Thiết kế host group và placement policy

Tạo nhóm host dành cho workload có license riêng. Thiết lập affinity, anti-affinity, IAM và policy triển khai. Xác định host dự phòng, vùng DR và quy tắc migration. Đảm bảo pipeline không thể đưa workload vào pool không được cấp phép.

### Bước 5: Xây dựng inventory và quy trình thay đổi

Liên kết license entitlement với host, VM, phần mềm và chủ sở hữu. Tự động thu thập inventory từ cloud API hoặc công cụ quản lý tài sản. Mỗi thay đổi tạo/xóa VM, đổi vCPU, migration hoặc thay host cần cập nhật lịch sử.

### Bước 6: Thử nghiệm hiệu năng, HA và kiểm toán

Đo hiệu năng CPU, bộ nhớ, NUMA, network và storage với tải đại diện. Thử host failure, maintenance, migration, scale-out và DR. Kiểm tra xem log và inventory có thể chứng minh vị trí workload trong một thời điểm quá khứ hay không.

### Bước 7: Tính TCO và phê duyệt kiến trúc

So sánh chi phí compute, license, dự phòng và vận hành. Ghi lại các giả định, rủi ro, điều khoản được xác nhận và điều kiện cần đánh giá lại. Sau khi phê duyệt, đưa các ràng buộc license vào IaC, policy và quy trình phát hành để duy trì lâu dài.

## 10. Ví dụ áp dụng

### Ví dụ 1: Cơ sở dữ liệu doanh nghiệp có license theo core vật lý

Một tổ chức vận hành cơ sở dữ liệu lớn, có hợp đồng BYOL với metric gắn với core vật lý. Đội ngũ cần biết chính xác host đang chạy database và giới hạn việc di chuyển workload.

**Phương án đánh giá:** dedicated host hoặc sole-tenant node có host ID, số core và placement metadata rõ ràng. Tạo host group riêng cho database, đặt affinity để VM chỉ chạy trên host được cấp phép. Dự phòng host thứ hai theo yêu cầu HA và xác nhận quyền license cho failover. Các API và worker không có ràng buộc này tiếp tục chạy ở shared pool.

**Điểm phải xác minh:** hợp đồng tính theo toàn bộ core hay core được phân bổ; cách xử lý SMT; quyền di chuyển; host thay thế; failover; và việc license có áp dụng cho node dự phòng hay không.

### Ví dụ 2: Ứng dụng thương mại được cấp phép theo VM

Một ứng dụng thương mại được tính license theo số VM có cài đặt phần mềm, với số vCPU tối đa và mức tối thiểu được quy định trong hợp đồng. Ứng dụng không cần host riêng và nhà cung cấp phần mềm cho phép triển khai trên môi trường ảo hóa cloud được chỉ định.

**Phương án đánh giá:** shared tenancy có thể phù hợp nếu đáp ứng yêu cầu bảo mật và điều khoản cloud. Quản lý số VM, cấu hình vCPU, template và autoscaling để tránh vượt số license. Pipeline cần kiểm tra entitlement trước khi tăng số instance.

**Điểm phải xác minh:** VM tắt có được tính không; clone hoặc snapshot có được xem là instance riêng không; số vCPU tối thiểu; quyền triển khai ở nhiều region; và quy tắc cấp phép cho môi trường DR.

### Ví dụ 3: Nền tảng phân tích cần hiệu năng và I/O ổn định

Một workload phân tích xử lý dữ liệu lớn, nhạy với băng thông bộ nhớ, NUMA và I/O. Nhóm kỹ thuật cần kiểm soát hệ điều hành hoặc hypervisor và muốn giảm biến động hiệu năng.

**Phương án đánh giá:** benchmark dedicated host và bare metal trên dữ liệu đại diện. So sánh CPU model, số core, topology NUMA, tốc độ mạng, loại storage và khả năng mở rộng. Nếu cần cài hypervisor riêng hoặc truy cập thiết bị đặc thù, bare metal có thể phù hợp. Nếu chỉ cần cô lập host và quản lý VM bằng cloud, dedicated host có thể đơn giản hơn.

**Điểm phải xác minh:** hiệu năng thực tế, thời gian cấp máy, quy trình vá firmware, khả năng thay host, HA, license của phần mềm phân tích và chi phí công suất nhàn rỗi.

## 11. Sai lầm thường gặp

- **Cho rằng dedicated instance tương đương dedicated host:** mức hiển thị host và quyền kiểm soát placement có thể khác nhau. Phải xác minh đúng cam kết dịch vụ.
- **Cho rằng dedicated hardware tự động hợp lệ cho BYOL:** điều khoản phần mềm mới quyết định quyền sử dụng. Tên dịch vụ cloud không thay thế hợp đồng.
- **Đồng nhất vCPU với core vật lý:** cách ánh xạ CPU ảo khác nhau giữa nền tảng và hợp đồng. Dùng sai đơn vị sẽ dẫn đến tính thiếu hoặc thừa license.
- **Chỉ cấp phép VM đang chạy:** VM dự phòng, cluster failover, DR, template hoặc VM tắt có thể được điều khoản xử lý riêng.
- **Bỏ qua migration và host replacement:** workload có thể chuyển sang host chưa được cấp phép hoặc làm thay đổi phạm vi kiểm toán.
- **Đặt mọi workload lên dedicated host:** tài nguyên nhàn rỗi và chi phí license có thể tăng. Chỉ dành riêng cho workload thực sự cần.
- **Không lưu lịch sử placement:** inventory hiện tại không chứng minh được vị trí phần mềm trong quá khứ.
- **Coi cô lập phần cứng là đủ bảo mật:** IAM, network policy, patching, encryption, logging và quản trị hệ điều hành vẫn cần thiết.
- **Quên license cho HA/DR:** host dự phòng có thể phát sinh nghĩa vụ cấp phép ngay cả khi chỉ chạy trong tình huống sự cố.
- **Không kiểm soát autoscaling:** scheduler có thể đưa workload sang host khác hoặc tạo nhiều VM hơn entitlement hiện có.

## 12. Checklist trước khi đưa workload lên dedicated hardware

- [ ] Đã xác định workload có yêu cầu cô lập vật lý, hiệu năng hay điều khoản license đặc biệt.
- [ ] Đã phân biệt dedicated instance, dedicated host, sole-tenant node và bare metal theo dịch vụ cụ thể.
- [ ] Đã đọc điều khoản license cho đúng sản phẩm, phiên bản và edition.
- [ ] Đã xác định metric: user, device, VM, vCPU, physical core, socket, host, cluster hoặc đơn vị khác.
- [ ] Đã xác minh quyền BYOL, license mobility, failover, DR, test và thời gian tái phân bổ.
- [ ] Đã xác định cách vCPU ánh xạ tới phần cứng và dữ liệu host cần lưu.
- [ ] Đã thiết kế host group, affinity, anti-affinity và giới hạn placement.
- [ ] Đã xác định host dự phòng, vùng triển khai và cách xử lý khi nhà cung cấp thay host.
- [ ] Đã có inventory nối entitlement với host, VM, phần mềm và lịch sử thay đổi.
- [ ] Đã kiểm soát IAM, network, encryption, patching và audit log.
- [ ] Đã thử nghiệm hiệu năng, mở rộng, host failure và DR.
- [ ] Đã tính TCO gồm compute, license, network, storage, vận hành và tài nguyên nhàn rỗi.
- [ ] Đã lưu xác nhận của nhà cung cấp phần mềm/cloud cho các điều khoản còn mơ hồ.

## 13. Kết luận

Dedicated instance, dedicated host, sole-tenant node và bare metal cung cấp các mức cô lập và kiểm soát phần cứng khác nhau. Dedicated instance thường hướng đến cô lập ở cấp instance; dedicated host hoặc sole-tenant node cho phép quản lý workload trên một máy chủ/node dành riêng; bare metal cung cấp quyền kiểm soát sâu hơn đối với máy vật lý và có thể cho phép khách hàng tự quản lý hypervisor.

Lựa chọn đúng phải dựa trên yêu cầu workload và điều khoản giấy phép phần mềm. Cần biết license được tính theo người dùng, thiết bị, VM, vCPU, core vật lý, socket, host hay cluster; đồng thời hiểu quyền BYOL, mobility, failover và DR. Sau khi chọn mô hình, hãy thực thi ràng buộc bằng placement policy, IAM, inventory và quy trình thay đổi. Cuối cùng, đánh giá TCO trên toàn bộ vòng đời, bao gồm license, host dự phòng và công suất nhàn rỗi, để kiến trúc vừa đáp ứng yêu cầu kỹ thuật vừa duy trì được khả năng kiểm toán.
