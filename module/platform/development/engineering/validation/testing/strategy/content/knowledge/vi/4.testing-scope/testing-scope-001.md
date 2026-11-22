# Xác định đối tượng kiểm thử: mã, dịch vụ, dữ liệu, cấu hình và sản phẩm triển khai

Trong chiến lược kiểm thử xác thực (**VALIDATION_TESTING_STRATEGY**), xác định đúng đối tượng kiểm thử là bước đầu để biến yêu cầu chất lượng thành hoạt động có thể thực hiện và đánh giá. Nếu phạm vi chỉ ghi chung chung như “kiểm thử chức năng thanh toán” hoặc “kiểm thử bản phát hành mới”, nhóm khó biết chính xác thành phần nào phải được kiểm tra, phiên bản nào đang được đánh giá và những phụ thuộc nào có thể làm thay đổi kết quả.

Đối tượng kiểm thử là phần tử cụ thể mà nhóm muốn xác minh một hoặc nhiều thuộc tính. Nó có thể là một đoạn mã, một dịch vụ, cấu trúc dữ liệu, cấu hình, gói phần mềm hoặc toàn bộ sản phẩm đã triển khai. Một phạm vi tốt cần mô tả các đối tượng này, mối liên hệ giữa chúng, ranh giới bao gồm và loại bằng chứng cần thu thập.

## 1. Đối tượng kiểm thử là gì?

Đối tượng kiểm thử (*test object*) là sản phẩm, thành phần, hệ thống hoặc phần tử được chọn để kiểm tra. Đối tượng có thể được xem xét ở nhiều mức độ chi tiết:

- Một hàm, lớp hoặc module trong mã nguồn.
- Một API, dịch vụ nền, worker, tiến trình định kỳ hoặc luồng xử lý sự kiện.
- Một bảng dữ liệu, schema, migration, tập dữ liệu hoặc trạng thái nghiệp vụ.
- Một tệp cấu hình, feature flag, chính sách phân quyền hoặc tham số triển khai.
- Một thư viện, package, container image hoặc gói cài đặt.
- Một ứng dụng hoàn chỉnh, một phiên bản phát hành hoặc một luồng người dùng xuyên suốt nhiều dịch vụ.

Đối tượng kiểm thử cần được định danh đủ rõ để người khác có thể xác định đúng thứ đã được kiểm tra. Ví dụ, “dịch vụ thanh toán” chưa đủ cụ thể nếu hệ thống có nhiều dịch vụ hoặc nhiều phiên bản. Có thể ghi “payment-api phiên bản 2.8.1, image digest sha256:…, triển khai trên môi trường staging với cấu hình cờ thanh toán mới”.

### 1.1. Phân biệt đối tượng kiểm thử với các khái niệm liên quan

Các khái niệm sau thường xuất hiện cùng nhau nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Đối tượng kiểm thử (test object) | Phần tử được kiểm tra. | API tạo đơn hàng, migration cơ sở dữ liệu, ứng dụng web. |
| Cơ sở kiểm thử (test basis) | Tài liệu hoặc nguồn thông tin dùng để xác định điều gì là đúng. | Yêu cầu, tiêu chí chấp nhận, hợp đồng API, quy tắc nghiệp vụ. |
| Điều kiện kiểm thử (test condition) | Khía cạnh hoặc hành vi cần được xác minh. | Người dùng không có quyền không thể xem đơn hàng của người khác. |
| Trường hợp kiểm thử (test case) | Đầu vào, điều kiện thực hiện và kết quả mong đợi cụ thể. | Gửi GET /orders/123 bằng tài khoản không sở hữu đơn hàng và xác nhận nhận phản hồi từ chối. |
| Môi trường kiểm thử (test environment) | Hạ tầng và cấu hình nơi việc kiểm thử được thực hiện. | Staging, phiên bản cơ sở dữ liệu, dịch vụ giả lập, mạng và tài khoản thử nghiệm. |

Phân biệt các khái niệm này giúp tránh việc ghi một yêu cầu hoặc một kịch bản như thể đó là đối tượng thực tế. Ví dụ, “đảm bảo không truy cập trái phép” là điều kiện cần xác minh; API và chính sách phân quyền là các đối tượng có thể được kiểm tra để thu thập bằng chứng cho điều kiện đó.

## 2. Các nhóm đối tượng cần xem xét

Không phải dự án nào cũng cần kiểm tra mọi nhóm. Hãy lựa chọn theo thay đổi, kiến trúc, rủi ro và mục tiêu phát hành. Tuy nhiên, nhóm nên rà soát đủ các nhóm dưới đây để tránh bỏ sót một thành phần có ảnh hưởng đến hành vi sản phẩm.

### 2.1. Mã nguồn và thành phần phần mềm

Mã nguồn có thể được kiểm tra ở mức hàm, lớp, module, thư viện hoặc package. Các thuộc tính thường được xác minh gồm:

- Logic nghiệp vụ và phép tính.
- Xử lý dữ liệu đầu vào, giá trị biên và trường hợp lỗi.
- Điều kiện, nhánh, vòng lặp và chuyển trạng thái.
- Xử lý ngoại lệ, timeout, retry và tài nguyên.
- Kiểm soát quyền truy cập và xử lý dữ liệu nhạy cảm.
- Khả năng tương thích với giao diện hoặc phiên bản thư viện khác.

Khi lập phạm vi, hãy ghi rõ đường dẫn hoặc tên module, phiên bản mã hoặc commit, cùng các thành phần bị ảnh hưởng. Một nhánh mã đã được kiểm tra trong commit cũ không tự động đại diện cho mã đã thay đổi sau đó.

Ví dụ:

| Đối tượng | Phần cần xác minh | Bằng chứng phù hợp |
|---|---|---|
| PriceCalculator | Thuế, giảm giá, làm tròn và giá trị biên. | Unit test với các phân vùng đầu vào và giá trị biên. |
| AccessPolicy | Quyền theo vai trò và quyền sở hữu tài nguyên. | Unit test và kiểm thử bảo mật ở mức API. |
| OrderRepository | Truy vấn, giao dịch và xử lý dữ liệu không tồn tại. | Component/integration test với cơ sở dữ liệu thử nghiệm. |

Không nên dùng danh sách file thay đổi làm toàn bộ phạm vi. Một thay đổi nhỏ có thể ảnh hưởng đến nhiều module dùng chung; ngược lại, một file thay đổi có thể không cần kiểm tra mọi hành vi của hệ thống. Hãy truy vết từ thay đổi đến hành vi và phụ thuộc liên quan.

### 2.2. Dịch vụ, API và luồng xử lý

Một dịch vụ có thể gồm nhiều giao diện và cơ chế xử lý: HTTP API, RPC, message consumer, scheduler, background worker hoặc luồng sự kiện. Đối tượng kiểm thử cần chỉ rõ giao diện và hành vi nào được bao gồm.

Với API, cần xác định endpoint, phương thức, schema yêu cầu/phản hồi, mã lỗi, xác thực, phân quyền, giới hạn tốc độ và tương thích phiên bản. Với dịch vụ xử lý sự kiện, cần xem xét định dạng thông điệp, thứ tự, xử lý trùng lặp, retry, dead-letter queue và tính idempotent khi phù hợp.

Ví dụ, phạm vi “dịch vụ đơn hàng” có thể được chia thành:

- API tạo đơn và truy vấn trạng thái.
- Consumer nhận sự kiện thanh toán.
- Worker cập nhật trạng thái đơn hàng hết hạn.
- Cơ chế gửi thông báo sau khi đơn được xác nhận.
- Giao tiếp với kho hàng và dịch vụ thanh toán.

Một kiểm thử API thành công chưa chứng minh các worker hoặc luồng sự kiện liên quan hoạt động đúng. Nếu các thành phần này thuộc luồng nghiệp vụ đang đánh giá, hãy đưa chúng vào phạm vi hoặc nêu rõ lý do chưa kiểm tra.

### 2.3. Dữ liệu, schema và trạng thái

Dữ liệu vừa là đầu vào, vừa có thể là đối tượng cần xác minh. Phạm vi dữ liệu nên bao gồm những khía cạnh có ảnh hưởng đến tính đúng đắn và an toàn của sản phẩm:

- Schema, kiểu dữ liệu, ràng buộc, chỉ mục và quan hệ.
- Migration, chuyển đổi, backfill và khả năng tương thích dữ liệu cũ.
- Quy tắc hợp lệ, tính đầy đủ, duy nhất và nhất quán.
- Trạng thái trước và sau thao tác; dữ liệu lịch sử và dữ liệu mới.
- Dữ liệu biên, dữ liệu lớn, dữ liệu thiếu hoặc không hợp lệ.
- Quyền truy cập, che giấu, lưu giữ và xóa dữ liệu.
- Khôi phục và tính toàn vẹn sau lỗi hoặc gián đoạn.

Cần ghi rõ loại dữ liệu và nguồn tạo dữ liệu kiểm thử. Dữ liệu tổng hợp, dữ liệu đã ẩn danh và bản sao dữ liệu thật có mức độ đại diện cũng như ràng buộc khác nhau. Nếu dùng dữ liệu đã ẩn danh, cần xác minh rằng quá trình biến đổi không làm mất các đặc điểm cần thiết cho kịch bản kiểm thử.

Không đưa thông tin bí mật hoặc dữ liệu cá nhân không cần thiết vào tài liệu phạm vi. Chỉ ghi mã định danh an toàn, loại dữ liệu, nguồn và cách chuẩn bị dữ liệu; thông tin xác thực nên được quản lý bằng cơ chế bí mật phù hợp.

### 2.4. Cấu hình và cờ tính năng

Cùng một mã nguồn có thể tạo ra hành vi khác nhau tùy cấu hình. Vì vậy, cấu hình cũng là một phần của phạm vi kiểm thử, đặc biệt khi thay đổi liên quan đến:

- Biến môi trường và tham số khởi động.
- Feature flag, toggle hoặc cấu hình bật/tắt tính năng.
- Chính sách phân quyền, giới hạn và quy tắc nghiệp vụ.
- Cấu hình kết nối, timeout, retry và pool tài nguyên.
- Cấu hình mạng, routing, TLS và chứng thư.
- Tham số triển khai, autoscaling, health check và resource limit.
- Cấu hình logging, metrics, tracing và cảnh báo.

Không cần liệt kê giá trị bí mật. Hãy định danh tên cấu hình, nguồn cấu hình, giá trị hoặc trạng thái không nhạy cảm cần kiểm tra, cùng môi trường áp dụng. Ví dụ: feature flag **new-checkout** bật trong nhóm người dùng thử nghiệm và tắt với nhóm còn lại.

Nếu có nhiều tổ hợp cấu hình, không nên mặc định rằng một tổ hợp đại diện cho tất cả. Hãy chọn tổ hợp theo rủi ro: cấu hình mặc định, cấu hình được khuyến nghị, cấu hình biên và những kết hợp có thể làm thay đổi hành vi quan trọng.

### 2.5. Sản phẩm và gói triển khai

Mã nguồn không phải lúc nào cũng giống thứ được đưa đến người dùng. Quá trình build, đóng gói, ký, phân phối và triển khai có thể tạo ra lỗi riêng. Vì vậy, khi xác minh bản phát hành, đối tượng cần được định danh ở dạng sản phẩm thực tế:

- Package, binary, ứng dụng cài đặt hoặc thư viện đã đóng gói.
- Container image và digest tương ứng.
- Manifest, chart hoặc bundle triển khai.
- Thành phần frontend đã build và tài nguyên tĩnh.
- Phiên bản ứng dụng di động hoặc desktop được phân phối.
- Bản phát hành đang chạy trên môi trường mục tiêu.

Cần ghi phiên bản, build number, commit hoặc artifact digest để bảo đảm kết quả kiểm thử gắn với đúng sản phẩm. Nếu kiểm thử một artifact nhưng sau đó triển khai artifact khác, kết quả trước đó không đủ để chứng minh artifact mới đã được xác minh.

Kiểm tra sản phẩm triển khai còn bao gồm việc xác nhận thành phần thực sự chạy đúng phiên bản, cấu hình được nạp đúng, health check hoạt động và các dịch vụ phụ thuộc được kết nối như dự kiến.

### 2.6. Sản phẩm nhìn từ luồng người dùng

Ở mức hệ thống, đối tượng kiểm thử có thể là một luồng hoàn chỉnh mà người dùng trải nghiệm, dù luồng đó đi qua nhiều dịch vụ và loại dữ liệu.

Ví dụ, luồng “đăng ký và kích hoạt tài khoản” có thể gồm giao diện đăng ký, API tạo tài khoản, cơ sở dữ liệu, dịch vụ gửi email, liên kết kích hoạt và cơ chế cập nhật trạng thái. Khi chọn luồng làm đối tượng kiểm thử, hãy ghi các thành phần cấu thành và điểm bắt đầu/kết thúc để nhóm hiểu phạm vi bao phủ.

Một luồng người dùng có thể được kiểm tra đầu cuối trong khi từng thành phần vẫn cần kiểm thử riêng để xác định lỗi nhanh và kiểm soát ranh giới. Hai cách nhìn bổ sung cho nhau.

## 3. Xác định ranh giới: bao gồm, loại trừ và phụ thuộc

Sau khi lập danh sách đối tượng, cần xác định rõ ranh giới của phạm vi. Ranh giới tốt giúp nhóm tránh hai tình huống: bỏ sót một phụ thuộc quan trọng hoặc mở rộng kiểm thử đến những phần không liên quan mà không có lý do.

### 3.1. Ghi rõ những gì được bao gồm

Với mỗi đối tượng, ghi ít nhất:

- Tên và loại đối tượng.
- Phiên bản, commit, build hoặc định danh artifact.
- Hành vi hoặc thuộc tính sẽ được xác minh.
- Mức kiểm thử dự kiến và bằng chứng cần thu thập.
- Môi trường, dữ liệu và cấu hình liên quan.
- Phụ thuộc có ảnh hưởng trực tiếp.

Ví dụ: “API POST /orders của order-service build 2026.11.16-rc2; xác minh tạo đơn, kiểm tra quyền, tính tổng tiền và xử lý yêu cầu lặp; chạy integration test trên staging với cơ sở dữ liệu phiên bản X và feature flag Y”.

### 3.2. Nêu rõ những gì bị loại trừ

Một phạm vi kiểm thử có thể có các phần loại trừ do giới hạn thời gian, quyền truy cập, môi trường hoặc mức rủi ro. Loại trừ cần được nêu rõ cùng lý do và ảnh hưởng dự kiến.

Ví dụ:

| Phần loại trừ | Lý do | Ảnh hưởng và xử lý |
|---|---|---|
| Kiểm thử với cổng thanh toán production | Không được phép tạo giao dịch thật trong giai đoạn xác minh. | Dùng sandbox và ghi rõ chưa có bằng chứng từ giao dịch production. |
| Kiểm thử tải ở quy mô cực đại | Môi trường staging không đủ tài nguyên. | Đánh giá riêng bằng môi trường tải chuyên dụng trước mốc phát hành. |
| Một trình duyệt cũ đã hết hỗ trợ | Nằm ngoài ma trận nền tảng được cam kết. | Ghi trong tiêu chí hỗ trợ và thông báo nếu có người dùng bị ảnh hưởng. |

Không nên ghi “ngoài phạm vi” mà không nêu tác động. Một phần bị loại trừ có thể vẫn chứa rủi ro đáng kể; người ra quyết định cần biết rủi ro đó được chấp nhận, giảm thiểu hay cần kiểm tra ở bước khác.

### 3.3. Lập bản đồ phụ thuộc

Một đối tượng hiếm khi hoạt động độc lập. Hãy lập bản đồ các phụ thuộc trực tiếp và gián tiếp có khả năng thay đổi kết quả, chẳng hạn:

- Dịch vụ nội bộ gọi qua API hoặc message broker.
- Cơ sở dữ liệu, cache, object storage và hệ thống tìm kiếm.
- Nhà cung cấp định danh, thanh toán, email hoặc bản đồ.
- Hạ tầng mạng, DNS, chứng thư và cân bằng tải.
- Thư viện, runtime, hệ điều hành và nền tảng triển khai.

Với mỗi phụ thuộc, xác định cách kiểm tra: dùng hệ thống thật, môi trường sandbox, contract test, mock hay stub. Ghi rõ ranh giới mô phỏng và điều gì chưa được chứng minh bởi cách mô phỏng đó.

## 4. Quy trình xác định đối tượng kiểm thử

Có thể thực hiện theo quy trình sau cho mỗi thay đổi hoặc bản phát hành.

### Bước 1: Xác định mục tiêu và cơ sở kiểm thử

Đọc yêu cầu, tiêu chí chấp nhận, thiết kế, hợp đồng giao tiếp và quy tắc nghiệp vụ liên quan. Xác định điều gì phải đúng, ai bị ảnh hưởng và hậu quả nếu sai.

### Bước 2: Lần theo thay đổi đến thành phần bị ảnh hưởng

Bắt đầu từ commit, yêu cầu hoặc luồng người dùng. Xác định mã nguồn, dịch vụ, API, dữ liệu, cấu hình và artifact có liên quan. Xem xét cả thành phần dùng chung và các luồng phụ thuộc.

### Bước 3: Chọn mức độ chi tiết phù hợp

Chia nhỏ thành đối tượng đủ cụ thể để giao người thực hiện và thu thập bằng chứng. Không cần tách mọi file thành một đối tượng riêng; nên nhóm theo ranh giới kỹ thuật hoặc hành vi có ý nghĩa.

### Bước 4: Đánh giá rủi ro và chọn cách kiểm tra

Ưu tiên đối tượng có tác động lớn, xác suất lỗi cao, thay đổi phức tạp hoặc khó phát hiện lỗi. Chọn unit, component, integration, contract, end-to-end hay kiểm thử phi chức năng tùy thuộc tính cần xác minh.

### Bước 5: Xác định môi trường, dữ liệu và cấu hình

Ghi phiên bản phụ thuộc, nguồn dữ liệu, trạng thái ban đầu, feature flag và cấu hình cần thiết để tái lập kết quả. Nêu rõ dịch vụ nào được thay thế bằng mô phỏng.

### Bước 6: Ghi ranh giới và khoảng trống

Liệt kê phần bao gồm, loại trừ, giả định, phụ thuộc chưa sẵn sàng và các rủi ro còn lại. Nếu một khoảng trống có thể ảnh hưởng đến quyết định phát hành, cần nêu hành động tiếp theo và người phụ trách.

### Bước 7: Liên kết đối tượng với bằng chứng

Mỗi đối tượng quan trọng cần được liên kết với điều kiện kiểm thử, ca kiểm thử, kết quả và lỗi tương ứng. Việc này giúp biết đối tượng nào chưa được kiểm tra và thay đổi nào có thể làm mất hiệu lực của bằng chứng trước đó.

## 5. Ví dụ: xác định phạm vi cho chức năng thanh toán

Giả sử một phiên bản mới thay đổi cách tính tổng tiền và tích hợp với nhà cung cấp thanh toán. Câu “kiểm thử chức năng thanh toán” chưa cho biết nhóm cần kiểm tra gì. Một phạm vi cụ thể có thể được mô tả như sau:

| Nhóm | Đối tượng kiểm thử | Nội dung xác minh |
|---|---|---|
| Mã nguồn | PriceCalculator | Giá sản phẩm, thuế, giảm giá, làm tròn và giá trị biên. |
| Mã nguồn | PaymentStateMachine | Chuyển trạng thái hợp lệ, từ chối chuyển trạng thái sai và xử lý lặp. |
| Dịch vụ | payment-api | Xác thực, phân quyền, schema, mã lỗi và idempotency key. |
| Dịch vụ | Payment callback handler | Chữ ký, thông điệp trùng lặp, callback đến trễ và retry. |
| Dữ liệu | Bảng payment và order | Ràng buộc, liên kết, trạng thái và tính nhất quán sau giao dịch. |
| Dữ liệu | Migration mới | Nâng cấp dữ liệu hiện có và khả năng tương thích với phiên bản trước. |
| Cấu hình | payment.provider, timeout và retry | Nạp đúng cấu hình, xử lý timeout và hành vi khi dịch vụ chậm. |
| Cấu hình | Feature flag new-payment-flow | Bật/tắt đúng nhóm người dùng và không ảnh hưởng luồng cũ. |
| Sản phẩm triển khai | Payment service image của release candidate | Đúng digest, cấu hình runtime, health check và khả năng khởi động. |
| Luồng người dùng | Thanh toán đơn hàng từ giao diện đến kết quả cuối | Tạo giao dịch, nhận callback và hiển thị trạng thái nhất quán. |

Phạm vi có thể ghi thêm:

- **Bao gồm:** unit test cho tính tiền và chuyển trạng thái; integration test với cơ sở dữ liệu; contract test với nhà cung cấp; end-to-end test trên sandbox; kiểm tra cấu hình bật/tắt feature flag.
- **Loại trừ:** giao dịch tiền thật trên production và tải cực đại trên hạ tầng production.
- **Giới hạn:** sandbox không tái hiện đầy đủ độ trễ và lỗi mạng của nhà cung cấp thật.
- **Bằng chứng cần có:** kết quả kiểm thử theo từng đối tượng, log/trace cho luồng lỗi, xác nhận digest của artifact và kết quả kiểm tra migration.
- **Rủi ro còn lại:** hành vi trong điều kiện tải production và sự cố riêng của nhà cung cấp cần được theo dõi khi triển khai có kiểm soát.

Ví dụ cho thấy một tính năng có thể liên quan đồng thời đến mã, dịch vụ, dữ liệu, cấu hình và sản phẩm triển khai. Nếu chỉ kiểm tra mã tính tiền, nhóm chưa có đủ bằng chứng về toàn bộ luồng thanh toán.

## 6. Mẫu ghi phạm vi kiểm thử

Có thể dùng mẫu sau để thống nhất cách mô tả phạm vi giữa người phát triển, người kiểm thử và người phê duyệt:

~~~text
Tên thay đổi / bản phát hành:
Mục tiêu kiểm thử:
Cơ sở kiểm thử (yêu cầu, tiêu chí chấp nhận, hợp đồng):

Đối tượng kiểm thử:
- Mã nguồn / module:
- Dịch vụ / API / worker:
- Dữ liệu / schema / migration:
- Cấu hình / feature flag:
- Artifact / sản phẩm triển khai:
- Luồng người dùng:

Định danh phiên bản:
Môi trường và cấu hình:
Dữ liệu kiểm thử và trạng thái ban đầu:
Phụ thuộc và cách mô phỏng:

Phạm vi bao gồm:
Phạm vi loại trừ:
Giả định và giới hạn:
Rủi ro còn lại:

Điều kiện cần xác minh:
Lớp kiểm thử và bằng chứng dự kiến:
Người phụ trách:
Tiêu chí hoàn tất:
~~~

Với dự án nhỏ, có thể gộp các mục không liên quan hoặc ghi “không áp dụng”, nhưng không nên bỏ trống một mục quan trọng mà không giải thích.

## 7. Duy trì phạm vi khi hệ thống thay đổi

Phạm vi kiểm thử không phải tài liệu cố định. Nó cần được xem xét lại khi có thay đổi về mã, schema, API, cấu hình, phụ thuộc, nền tảng hoặc artifact triển khai.

Khi có thay đổi, hãy xác định:

1. Đối tượng nào đã thay đổi trực tiếp?
2. Đối tượng nào phụ thuộc vào phần thay đổi?
3. Điều kiện kiểm thử hoặc ca kiểm thử nào bị ảnh hưởng?
4. Bằng chứng trước đó còn áp dụng cho phiên bản hiện tại không?
5. Có cần bổ sung kiểm thử hồi quy hoặc kiểm thử trên môi trường khác không?

Ví dụ, thay đổi schema có thể ảnh hưởng đến dịch vụ đọc dữ liệu, báo cáo, worker và khả năng rollback. Thay đổi một feature flag có thể tạo thêm nhánh hành vi cần xác minh. Cập nhật thư viện nền tảng có thể ảnh hưởng đến nhiều dịch vụ dù mã nghiệp vụ không đổi.

Nên lưu dấu phiên bản của đối tượng cùng kết quả kiểm thử. Khi phiên bản thay đổi, nhóm có thể xác định bằng chứng nào cần chạy lại thay vì mặc định rằng kết quả cũ vẫn còn hiệu lực.

## 8. Những sai lầm thường gặp

- **Chỉ ghi tên tính năng:** tên tính năng không xác định được thành phần, phiên bản và ranh giới cần kiểm tra. Hãy phân rã thành mã, dịch vụ, dữ liệu, cấu hình và artifact liên quan.
- **Chỉ kiểm thử mã nguồn:** hành vi sản phẩm còn phụ thuộc vào build, cấu hình, dữ liệu, tích hợp và môi trường triển khai.
- **Quên dữ liệu và migration:** mã mới có thể chạy đúng với dữ liệu sạch nhưng lỗi khi xử lý dữ liệu cũ hoặc dữ liệu không nhất quán.
- **Coi mock là hệ thống thật:** mock giúp cô lập thành phần nhưng không chứng minh tích hợp thực tế hoạt động đúng.
- **Không định danh phiên bản:** nếu không biết commit hoặc artifact nào đã được kiểm tra, kết quả khó tái lập và khó áp dụng cho quyết định phát hành.
- **Không ghi phần loại trừ:** người đọc có thể hiểu nhầm rằng mọi rủi ro đã được bao phủ.
- **Không cập nhật phạm vi sau thay đổi:** bằng chứng cũ có thể không còn phù hợp với mã hoặc cấu hình mới.

## 9. Danh sách rà soát trước khi chốt phạm vi

- [ ] Mục tiêu và cơ sở kiểm thử được xác định.
- [ ] Đối tượng được phân rã đủ rõ theo mã, dịch vụ, dữ liệu, cấu hình và sản phẩm triển khai khi có liên quan.
- [ ] Mỗi đối tượng quan trọng có định danh phiên bản hoặc artifact.
- [ ] Hành vi và thuộc tính cần xác minh được mô tả.
- [ ] Môi trường, dữ liệu và cấu hình có thể tái lập được ghi rõ.
- [ ] Phụ thuộc nội bộ và bên ngoài được lập bản đồ.
- [ ] Ranh giới bao gồm và loại trừ có lý do.
- [ ] Mock, stub, sandbox và giới hạn mô phỏng được nêu rõ.
- [ ] Đối tượng được liên kết với ca kiểm thử và bằng chứng dự kiến.
- [ ] Có cách đánh giá lại phạm vi khi mã, dữ liệu, cấu hình hoặc artifact thay đổi.

## Kết luận

Xác định đối tượng kiểm thử giúp nhóm biết chính xác phần nào của hệ thống đang được đánh giá và bằng chứng nào cần thu thập. Một phạm vi đáng tin cậy cần nhìn xuyên suốt từ mã nguồn đến dịch vụ, dữ liệu, cấu hình và sản phẩm thực tế được triển khai; đồng thời nêu rõ phiên bản, phụ thuộc, ranh giới và phần chưa được xác minh. Khi phạm vi được mô tả cụ thể, hoạt động kiểm thử dễ phân công, tái lập và gắn kết quả với quyết định phát hành hơn.
