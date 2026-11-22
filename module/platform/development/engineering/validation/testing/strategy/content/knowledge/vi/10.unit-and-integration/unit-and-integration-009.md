# Phân công trách nhiệm kiểm tra lỗi tại từng điểm tích hợp

Lỗi tích hợp thường xuất hiện khi hai hoặc nhiều thành phần phối hợp với nhau: một dịch vụ gửi dữ liệu mà dịch vụ nhận hiểu khác, một sự kiện bị giao nhiều lần, một giao dịch chỉ hoàn tất ở một hệ thống, hoặc một thay đổi cấu hình khiến kết nối không còn hoạt động. Mỗi thành phần có thể vượt qua kiểm thử riêng nhưng toàn bộ tương tác vẫn sai.

Để phát hiện những lỗi này, nhóm cần phân công trách nhiệm kiểm tra tại từng điểm tích hợp. Mỗi điểm cần có người hoặc nhóm hiểu hợp đồng, xác định các tình huống lỗi, duy trì phép kiểm chứng và theo dõi kết quả. Với tích hợp liên quan nhiều nhóm, cần một đầu mối chịu trách nhiệm điều phối để các phần kiểm tra không bị bỏ trống giữa ranh giới tổ chức.

Phân công rõ ràng không có nghĩa một nhóm phải tự kiểm tra mọi thứ. Nhóm cung cấp thành phần chịu trách nhiệm về hành vi và hợp đồng mà mình công bố; nhóm sử dụng thành phần chịu trách nhiệm kiểm tra cách tích hợp và xử lý phản hồi; nhóm nền tảng hoặc vận hành chịu trách nhiệm về hạ tầng và khả năng quan sát thuộc phạm vi của họ. Một chủ sở hữu luồng hoặc tích hợp cần bảo đảm các bằng chứng này kết nối thành bức tranh đầy đủ.

## 1. Điểm tích hợp là gì và vì sao cần phân công?

Điểm tích hợp là ranh giới nơi các thành phần trao đổi dữ liệu, gọi chức năng, chia sẻ trạng thái hoặc phụ thuộc vào khả năng của nhau. Điểm này có thể nằm giữa hai dịch vụ, giữa ứng dụng và cơ sở dữ liệu, giữa một hệ thống nội bộ và nhà cung cấp bên ngoài, hoặc giữa mã ứng dụng với hạ tầng triển khai.

Ví dụ về điểm tích hợp:

- Một dịch vụ gọi API của dịch vụ khác.
- Một dịch vụ phát sự kiện và một dịch vụ khác tiêu thụ sự kiện đó.
- Ứng dụng ghi dữ liệu qua lớp truy cập cơ sở dữ liệu.
- Một quy trình batch xuất tệp để hệ thống khác nhập.
- Dịch vụ xác thực phát hành token để các API kiểm tra quyền.
- Ứng dụng gửi yêu cầu đến cổng thanh toán hoặc nhà cung cấp vận chuyển.
- Một migration thay đổi cấu trúc dữ liệu mà nhiều phiên bản ứng dụng cùng sử dụng.
- Một dịch vụ được triển khai với cấu hình mạng, chứng thư hoặc thông tin xác thực do nền tảng quản lý.

Điểm tích hợp có rủi ro vì mỗi phía có thể dựa trên giả định khác nhau. Một dịch vụ gửi trường amount theo đơn vị đồng, trong khi phía nhận hiểu là đơn vị nhỏ hơn; một bên coi timeout là thất bại, bên kia đã xử lý thành công; một sự kiện có thể đến trễ hoặc lặp lại; hoặc quyền truy cập hợp lệ trong môi trường thử nghiệm lại bị từ chối trong môi trường triển khai.

Nếu trách nhiệm không rõ, các nhóm dễ cho rằng bên kia đang kiểm tra. Nhà cung cấp API có thể kiểm thử hàm xử lý riêng, bên tiêu thụ có thể kiểm thử mã gọi riêng, nhưng không ai xác minh hợp đồng và hành vi thực tế tại ranh giới. Lỗi chỉ xuất hiện khi triển khai hoặc khi có dữ liệu thật.

### Những câu hỏi phải trả lời cho mỗi điểm tích hợp

Với mỗi ranh giới, nhóm cần xác định:

1. Thành phần nào cung cấp và thành phần nào sử dụng giao tiếp?
2. Hợp đồng dữ liệu và hành vi được định nghĩa ở đâu?
3. Những lỗi nào có thể xuất hiện tại ranh giới?
4. Phép kiểm chứng nào xác nhận tương tác đúng?
5. Nhóm nào viết, duy trì và thực thi kiểm thử?
6. Ai xử lý lỗi khi kiểm thử thất bại?
7. Bằng chứng được lưu ở đâu và ai theo dõi?
8. Điều gì xảy ra khi phụ thuộc chậm, ngừng hoạt động hoặc trả kết quả không chắc chắn?

Nếu chưa thể trả lời một trong những câu hỏi quan trọng này, điểm tích hợp có thể đang thiếu trách nhiệm hoặc thiếu bằng chứng.

## 2. Phân loại điểm tích hợp trước khi giao trách nhiệm

Không phải mọi điểm tích hợp đều có cùng kiểu rủi ro. Việc phân loại giúp nhóm xác định loại kiểm tra và chuyên môn cần thiết.

| Loại điểm tích hợp | Ví dụ | Rủi ro thường gặp |
|---|---|---|
| API đồng bộ | REST, GraphQL, gRPC | Sai schema, mã trạng thái, timeout, xác thực, tương thích phiên bản |
| Sự kiện và hàng đợi | Message broker, event bus | Mất, lặp, trễ hoặc sai thứ tự thông điệp; xử lý không idempotent |
| Cơ sở dữ liệu | Ứng dụng với DB hoặc nhiều dịch vụ cùng truy cập dữ liệu | Sai kiểu dữ liệu, transaction, khóa, migration, tính nhất quán |
| Tệp và batch | CSV, JSON, tệp trao đổi theo lịch | Sai định dạng, mã hóa, bản ghi thiếu, xử lý lặp hoặc tệp đến trễ |
| Xác thực và danh tính | OAuth, OIDC, token, identity provider | Token hết hạn, sai audience, quyền quá rộng hoặc thu hồi không hiệu lực |
| Hệ thống bên ngoài | Thanh toán, vận chuyển, email, bản đồ | Phụ thuộc không sẵn sàng, giới hạn tốc độ, thay đổi hợp đồng, kết quả không chắc chắn |
| Hạ tầng và triển khai | DNS, mạng, chứng thư, secret, cấu hình | Kết nối thất bại, cấu hình sai, chứng thư hết hạn, thiếu quyền |
| Migration và tương thích dữ liệu | Nâng cấp schema, thay đổi định dạng | Phiên bản cũ và mới không tương thích, chuyển đổi mất dữ liệu |

Một hệ thống có thể có nhiều loại điểm tích hợp trên cùng một luồng nghiệp vụ. Ví dụ, đặt hàng có thể gọi API kiểm tra tồn kho, ghi đơn vào cơ sở dữ liệu, phát sự kiện, gọi dịch vụ thanh toán và nhận webhook. Mỗi ranh giới cần có phạm vi kiểm chứng và chủ sở hữu cụ thể.

## 3. Xác định các vai trò chịu trách nhiệm

Phân công hiệu quả cần tách rõ trách nhiệm về hợp đồng, mã nguồn, kiểm thử, hạ tầng và luồng nghiệp vụ. Một nhóm có thể đảm nhận nhiều vai trò, nhưng trách nhiệm cuối cùng phải rõ.

### Nhóm cung cấp thành phần (provider)

Nhóm cung cấp chịu trách nhiệm về giao diện mà thành phần công bố. Họ cần:

- Định nghĩa và duy trì hợp đồng API, schema sự kiện hoặc định dạng dữ liệu.
- Làm rõ ý nghĩa trường dữ liệu, đơn vị đo, trạng thái và quy tắc lỗi.
- Kiểm tra đầu vào, đầu ra và các điều kiện biên thuộc thành phần.
- Duy trì kiểm thử đơn vị, thành phần và kiểm thử hợp đồng phía cung cấp.
- Thông báo thay đổi có thể ảnh hưởng đến bên tiêu thụ.
- Cung cấp cách mô phỏng hoặc môi trường kiểm thử khi cần.
- Điều tra lỗi nằm trong hành vi của thành phần cung cấp.

Nhóm cung cấp không thể giả định rằng bên tiêu thụ sẽ tự phát hiện mọi thay đổi phá vỡ tương thích.

### Nhóm sử dụng thành phần (consumer)

Nhóm sử dụng chịu trách nhiệm về cách họ gọi và diễn giải thành phần phụ thuộc. Họ cần:

- Dùng hợp đồng đúng phiên bản và truyền dữ liệu theo quy tắc.
- Kiểm tra cách xử lý phản hồi thành công, lỗi, timeout và dữ liệu bất thường.
- Duy trì kiểm thử phía tiêu thụ để xác nhận kỳ vọng của mình.
- Xử lý retry, timeout, circuit breaker và idempotency phù hợp với giao thức.
- Không giả định rằng phụ thuộc luôn sẵn sàng hoặc phản hồi đúng thứ tự.
- Điều tra lỗi trong cách tích hợp, chuyển đổi hoặc sử dụng dữ liệu.
- Cập nhật kiểm thử khi hợp đồng hoặc nhu cầu nghiệp vụ thay đổi.

Nhóm sử dụng phải kiểm tra cả cách hệ thống của mình phản ứng với lỗi từ bên ngoài, không chỉ xác nhận rằng yêu cầu được gửi đi.

### Chủ sở hữu điểm tích hợp hoặc luồng nghiệp vụ

Với điểm tích hợp xuyên nhóm, cần một đầu mối điều phối. Vai trò này có thể thuộc nhóm sở hữu luồng nghiệp vụ, nhóm nền tảng tích hợp hoặc một nhóm dịch vụ được chỉ định. Trách nhiệm gồm:

- Bảo đảm hợp đồng và ranh giới được ghi nhận.
- Xác định rủi ro xuyên thành phần và phép kiểm chứng cần thiết.
- Phân chia công việc giữa provider, consumer và nhóm hỗ trợ.
- Bảo đảm có kiểm thử tích hợp hoặc kiểm thử hợp đồng tại nơi phù hợp.
- Theo dõi các lỗi chưa được phân loại hoặc đang chờ nhóm khác xử lý.
- Bảo đảm bằng chứng từ các nhóm được liên kết và có thể truy vết.
- Điều phối quyết định khi có bất đồng về nguyên nhân hoặc trách nhiệm.

Đầu mối này không nhất thiết phải tự viết mọi kiểm thử. Họ chịu trách nhiệm bảo đảm không có khoảng trống giữa các nhóm.

### Nhóm nền tảng và vận hành

Nhóm nền tảng hoặc vận hành thường sở hữu môi trường, mạng, pipeline, broker, chứng thư, secret, giám sát và cảnh báo. Họ cần:

- Cung cấp môi trường và cấu hình có thể tái tạo.
- Kiểm tra khả năng kết nối, phân quyền hạ tầng và cấu hình triển khai.
- Hỗ trợ mô phỏng lỗi phụ thuộc hoặc sự cố hạ tầng.
- Duy trì log, metric, trace và cảnh báo cho các điểm tích hợp.
- Hỗ trợ điều tra timeout, lỗi mạng, hàng đợi và sự cố tài nguyên.
- Xác minh khả năng phục hồi và quy trình vận hành theo phạm vi được giao.

Nhóm nền tảng không thay thế trách nhiệm kiểm thử nghiệp vụ của provider hoặc consumer. Một broker hoạt động bình thường không chứng minh thông điệp được xử lý đúng.

### Nhóm kiểm thử hoặc chất lượng

Nhóm kiểm thử hỗ trợ thiết kế chiến lược, rà soát khoảng trống và cung cấp góc nhìn xuyên suốt. Họ có thể:

- Phân tích rủi ro tại các điểm tích hợp.
- Xác định tình huống kiểm thử đại diện và tình huống lỗi.
- Hỗ trợ kiểm thử hợp đồng, tích hợp, hệ thống và thăm dò.
- Đánh giá chất lượng bằng chứng và mức bao phủ.
- Điều phối phiên kiểm thử giữa các nhóm.
- Theo dõi lỗi xuyên nhóm và xác nhận kiểm thử hồi quy.

Trách nhiệm chất lượng là trách nhiệm chung. Không nên giao toàn bộ việc bảo đảm tích hợp cho một nhóm kiểm thử độc lập nếu các nhóm sở hữu thành phần không tham gia duy trì kiểm thử.

## 4. Phân biệt người chịu trách nhiệm, người thực hiện và người phối hợp

Để tránh mơ hồ, có thể sử dụng mô hình RACI:

- **R – Responsible:** người hoặc nhóm trực tiếp thực hiện công việc.
- **A – Accountable:** người hoặc nhóm chịu trách nhiệm cuối cùng về kết quả.
- **C – Consulted:** bên cần tham vấn vì có kiến thức hoặc phụ thuộc liên quan.
- **I – Informed:** bên cần được thông báo về kết quả hoặc thay đổi.

Với mỗi đầu việc quan trọng, nên có một đầu mối A rõ ràng. Có thể có nhiều R và C. Nếu một công việc có nhiều A nhưng không thống nhất quyền quyết định, trách nhiệm dễ bị phân tán.

Ví dụ cho một API kiểm tra tồn kho:

| Công việc | Provider tồn kho | Consumer đơn hàng | Nhóm tích hợp | Nền tảng |
|---|---|---|---|---|
| Định nghĩa schema và ý nghĩa phản hồi | A/R | C | C | I |
| Kiểm tra logic nội bộ của API | A/R | I | C | I |
| Kiểm tra cách consumer xử lý phản hồi | C | A/R | C | I |
| Kiểm thử hợp đồng giữa hai bên | R | R | A | I |
| Kiểm thử tích hợp trên môi trường chung | R | R | A | C |
| Kiểm tra mạng, secret và cấu hình | C | C | I | A/R |
| Điều tra lỗi xuyên ranh giới | R | R | A điều phối | C |
| Theo dõi bằng chứng và khoảng trống | C | C | A/R | C |

Ma trận chỉ là ví dụ. Tổ chức cần thay vai trò bằng nhóm và người sở hữu thực tế. Với một điểm tích hợp đơn giản nằm hoàn toàn trong một nhóm, không cần tạo quy trình RACI phức tạp; chỉ cần ghi rõ người sở hữu và cách kiểm chứng.

## 5. Phân công theo từng loại điểm tích hợp

### API đồng bộ

Với API, provider chịu trách nhiệm định nghĩa schema, xác thực, mã trạng thái, ý nghĩa lỗi và quy tắc tương thích. Consumer chịu trách nhiệm gửi yêu cầu hợp lệ, xử lý phản hồi và hành vi khi timeout hoặc dữ liệu không hợp lệ.

Các kiểm tra nên bao gồm:

- Trường bắt buộc, kiểu dữ liệu, định dạng và giới hạn.
- Mã trạng thái và cấu trúc lỗi.
- Xác thực, phân quyền và quyền truy cập tài nguyên.
- Giá trị biên và dữ liệu không hợp lệ.
- Timeout, retry và giới hạn tốc độ.
- Tương thích giữa phiên bản provider và consumer.
- Tính idempotent với thao tác có thể gửi lặp.
- Hành vi khi provider trả dữ liệu thiếu hoặc không đúng hợp đồng.

Kiểm thử hợp đồng có thể được thực hiện ở cả phía provider và consumer. Provider xác nhận API đáp ứng hợp đồng công bố; consumer xác nhận kỳ vọng của mình phù hợp với hợp đồng. Một bước xác minh kết hợp giúp phát hiện bất tương thích trước khi triển khai chung.

### Sự kiện và hàng đợi thông điệp

Trong hệ thống bất đồng bộ, provider thường chịu trách nhiệm về schema, ý nghĩa và thời điểm phát sự kiện. Consumer chịu trách nhiệm xử lý thông điệp theo hợp đồng, quản lý lỗi và tránh tác động lặp. Nhóm sở hữu broker hoặc nền tảng chịu trách nhiệm cấu hình giao nhận, quyền và khả năng quan sát hạ tầng.

Cần kiểm tra:

- Schema, phiên bản và khả năng tương thích sự kiện.
- Mã định danh duy nhất và thông tin tương quan.
- Thông điệp lặp, đến trễ hoặc sai thứ tự.
- Consumer xử lý lỗi một phần và retry.
- Dead-letter queue và quy trình xử lý thông điệp lỗi.
- Thời hạn lưu trữ, xác nhận và khả năng phát lại.
- Tính idempotent và tính nhất quán của dữ liệu sau xử lý.
- Quyền phát và tiêu thụ sự kiện.

Một kiểm thử consumer đơn vị có thể xác minh logic khi nhận thông điệp lặp, nhưng kiểm thử tích hợp cần xác minh hành vi với broker và cơ chế xác nhận thực tế. Cần chỉ rõ ai sở hữu từng phần.

### Cơ sở dữ liệu và chia sẻ dữ liệu

Khi một ứng dụng truy cập cơ sở dữ liệu, nhóm phát triển thành phần thường chịu trách nhiệm về truy vấn, transaction và ánh xạ dữ liệu. Nhóm dữ liệu hoặc nền tảng chịu trách nhiệm về cấu hình, quyền, sao lưu, hiệu năng và vận hành cơ sở dữ liệu.

Nếu nhiều dịch vụ cùng truy cập một kho dữ liệu, cần xác định rõ quyền sở hữu schema và dữ liệu. Không nên để nhiều nhóm thay đổi cấu trúc mà không có quy trình tương thích.

Các kiểm tra quan trọng:

- Kiểu dữ liệu, ràng buộc, khóa và chỉ mục.
- Transaction và tính nguyên tử.
- Truy cập đồng thời, khóa và deadlock.
- Migration tiến và lùi, nếu được hỗ trợ.
- Tương thích giữa phiên bản ứng dụng cũ và schema mới.
- Quyền truy cập tối thiểu.
- Tính nhất quán và khả năng phục hồi sau lỗi.
- Sao lưu, khôi phục và kiểm tra dữ liệu sau chuyển đổi.

Với migration, cần có chủ sở hữu chịu trách nhiệm xác minh cả dữ liệu trước và sau chuyển đổi. Chạy migration thành công không chứng minh dữ liệu đã được chuyển đúng.

### Tích hợp với hệ thống bên ngoài

Provider bên ngoài có thể thay đổi, giới hạn tốc độ hoặc không bảo đảm môi trường thử nghiệm giống sản xuất. Nhóm sử dụng dịch vụ chịu trách nhiệm về cách tích hợp và hành vi dự phòng. Nhóm quản lý nhà cung cấp hoặc kiến trúc có thể hỗ trợ hợp đồng, điều khoản và thông báo thay đổi.

Cần kiểm tra:

- Xác thực và quản lý thông tin truy cập.
- Schema, phiên bản API và thông báo thay đổi.
- Timeout, retry, giới hạn tốc độ và circuit breaker.
- Kết quả không chắc chắn sau timeout.
- Webhook lặp hoặc đến sai thứ tự.
- Môi trường sandbox và khác biệt với sản xuất.
- Hành vi dự phòng khi dịch vụ ngừng hoạt động.
- Đối soát giao dịch hoặc dữ liệu khi hai hệ thống lệch nhau.

Không thể kiểm soát toàn bộ hệ thống của nhà cung cấp, nhưng nhóm vẫn chịu trách nhiệm kiểm tra cách sản phẩm phản ứng khi phụ thuộc hoạt động sai hoặc không sẵn sàng.

### Tích hợp xác thực và danh tính

Nhóm sở hữu cơ chế xác thực hoặc identity provider chịu trách nhiệm về phát hành, xác minh và thu hồi danh tính. Nhóm sở hữu API chịu trách nhiệm áp dụng đúng chính sách quyền tại tài nguyên của mình.

Các tình huống cần kiểm tra:

- Token hợp lệ, hết hạn, bị thu hồi hoặc sai audience.
- Chữ ký, issuer và thuật toán được chấp nhận.
- Quyền theo vai trò, phạm vi và tài nguyên.
- Truy cập chéo người dùng hoặc tổ chức.
- Thay đổi quyền trong lúc phiên đang hoạt động.
- Hành vi khi identity provider không sẵn sàng.
- Thông tin nhạy cảm trong token, log và phản hồi.

Một lần đăng nhập thành công không chứng minh phân quyền ở mọi API là đúng. Mỗi API nhạy cảm cần có kiểm tra tại điểm thực thi.

### Tích hợp tệp và batch

Với tệp trao đổi, nhóm tạo tệp chịu trách nhiệm về cấu trúc và chất lượng dữ liệu đầu ra; nhóm nhập chịu trách nhiệm xác thực, xử lý dữ liệu sai và tránh nhập trùng; nhóm điều phối batch chịu trách nhiệm lịch chạy, truyền nhận và cảnh báo.

Cần kiểm tra:

- Định dạng, encoding, delimiter, header và phiên bản schema.
- Trường bắt buộc, giá trị biên và dữ liệu sai.
- Tệp rỗng, tệp lớn, tệp bị cắt hoặc gửi trùng.
- Quy tắc đặt tên, chữ ký hoặc checksum nếu áp dụng.
- Thời điểm đến, múi giờ và lịch chạy.
- Xử lý một phần thành công và khả năng chạy lại.
- Đối soát số lượng bản ghi và tổng giá trị.
- Quyền truy cập và lưu trữ an toàn.

### Tích hợp hạ tầng và cấu hình triển khai

Nhóm nền tảng chịu trách nhiệm về mạng, DNS, chứng thư, secret, quyền dịch vụ và cấu hình môi trường. Nhóm ứng dụng chịu trách nhiệm khai báo các phụ thuộc và xác minh hành vi khi cấu hình thiếu hoặc sai.

Cần kiểm tra:

- Kết nối giữa các thành phần trong môi trường triển khai.
- Chứng thư còn hiệu lực và xác minh danh tính đầu kia.
- Secret được cấp đúng, không ghi vào log hoặc mã nguồn.
- Quyền dịch vụ theo nguyên tắc tối thiểu.
- Cấu hình giữa môi trường kiểm thử và sản xuất.
- Thứ tự triển khai và khả năng tương thích phiên bản.
- Health check, readiness và khả năng khởi động lại.
- Hành vi khi một cấu hình bắt buộc bị thiếu.

## 6. Xác định ai viết và duy trì từng loại kiểm thử

Phân công theo tầng cần được chuyển thành công việc cụ thể. Một mô hình tham khảo:

| Loại kiểm thử | Người viết chính | Bên phối hợp | Người duy trì kết quả |
|---|---|---|---|
| Kiểm thử đơn vị của provider | Nhóm provider | Nhóm kiểm thử khi cần | Nhóm provider |
| Kiểm thử đơn vị của consumer | Nhóm consumer | Nhóm kiểm thử khi cần | Nhóm consumer |
| Kiểm thử hợp đồng provider | Nhóm provider | Consumer, nhóm tích hợp | Provider và đầu mối hợp đồng |
| Kiểm thử hợp đồng consumer | Nhóm consumer | Provider, nhóm tích hợp | Consumer và đầu mối hợp đồng |
| Kiểm thử tích hợp hai thành phần | Các nhóm sở hữu hai phía | Nhóm tích hợp, nền tảng | Chủ sở hữu luồng hoặc tích hợp |
| Kiểm thử đầu cuối nghiệp vụ | Nhóm sở hữu luồng hoặc kiểm thử | Provider, consumer, sản phẩm | Chủ sở hữu luồng |
| Kiểm tra cấu hình và hạ tầng | Nhóm nền tảng | Nhóm ứng dụng | Nhóm nền tảng |
| Kiểm tra sau triển khai | Nhóm vận hành và nhóm dịch vụ | Chủ sở hữu luồng | Nhóm vận hành cùng chủ sở hữu dịch vụ |

Không nhất thiết phải có một nhóm tích hợp chuyên trách. Trong nhóm nhỏ, kỹ sư sở hữu luồng có thể đảm nhận vai trò điều phối. Trong tổ chức nhiều nhóm, có thể cần một nhóm nền tảng hoặc kiến trúc chịu trách nhiệm tiêu chuẩn hóa hợp đồng và môi trường kiểm thử.

Điều quan trọng là tên người viết kiểm thử không thay thế trách nhiệm duy trì. Khi mã nguồn, hợp đồng hoặc dữ liệu thay đổi, chủ sở hữu phải biết kiểm thử nào cần cập nhật và ai xác nhận kết quả.

## 7. Quy trình phân công trách nhiệm tại một điểm tích hợp

Có thể sử dụng quy trình sau khi thêm tích hợp mới hoặc thay đổi tích hợp hiện có.

### Bước 1: Ghi nhận ranh giới

Xác định provider, consumer, giao thức, dữ liệu, môi trường và chủ sở hữu hai phía. Nếu có bên ngoài, ghi nhận đầu mối kỹ thuật và giới hạn của sandbox.

### Bước 2: Định nghĩa hợp đồng

Ghi rõ schema, ý nghĩa trường, đơn vị, trạng thái, lỗi, timeout, retry, phiên bản và quy tắc tương thích. Với sự kiện, bổ sung định danh, thứ tự và khả năng phát lại.

### Bước 3: Phân tích lỗi có thể xảy ra

Xem xét dữ liệu sai, quyền sai, timeout, gửi lặp, mất kết nối, xử lý một phần, phiên bản không tương thích và thay đổi cấu hình. Ưu tiên tình huống có hậu quả lớn.

### Bước 4: Chọn phép kiểm chứng và tầng

Xác định phần nào được kiểm tra ở đơn vị, thành phần, hợp đồng, tích hợp, đầu cuối hoặc vận hành. Mỗi phép kiểm chứng phải có mục tiêu rõ và không dựa vào giả định rằng một tầng khác đã kiểm tra.

### Bước 5: Phân công người thực hiện và đầu mối

Chỉ định nhóm viết, nhóm duy trì, nhóm chạy, người xử lý lỗi và đầu mối điều phối. Ghi nhận cách phối hợp khi lỗi nằm giữa hai thành phần.

### Bước 6: Chuẩn bị môi trường và dữ liệu

Bảo đảm dữ liệu có thể tái tạo, phụ thuộc có thể giả lập hoặc truy cập an toàn, cấu hình được quản lý và kết quả có thể quan sát.

### Bước 7: Đưa kiểm thử vào quy trình

Xác định kiểm thử nào chạy khi thay đổi mã, khi hợp nhất, theo lịch, trước phát hành và sau triển khai. Quy định điều kiện chặn và cách xử lý khi công cụ hoặc môi trường không khả dụng.

### Bước 8: Theo dõi và cập nhật

Khi có lỗi hoặc thay đổi hợp đồng, cập nhật ma trận trách nhiệm, kiểm thử và tài liệu. Sau sự cố, xem xét liệu phép kiểm chứng hiện tại có tạo đúng điều kiện lỗi và có người theo dõi kết quả hay không.

## 8. Ví dụ tổng hợp: phân công trách nhiệm trong luồng đặt hàng

Giả sử một ứng dụng thương mại điện tử có các thành phần:

- Dịch vụ đơn hàng tạo và quản lý trạng thái đơn.
- Dịch vụ tồn kho giữ chỗ và trừ số lượng sản phẩm.
- Dịch vụ thanh toán xử lý giao dịch với nhà cung cấp.
- Broker truyền sự kiện giữa các dịch vụ.
- Dịch vụ thông báo gửi email hoặc tin nhắn cho người dùng.

Luồng nghiệp vụ là: khách hàng xác nhận giỏ hàng, hệ thống kiểm tra tồn kho, tạo đơn, giữ chỗ, thanh toán, xác nhận đơn và gửi thông báo.

### Bản đồ điểm tích hợp

| Điểm tích hợp | Dữ liệu hoặc hành vi | Rủi ro chính |
|---|---|---|
| Đơn hàng → Tồn kho | Yêu cầu giữ chỗ, mã sản phẩm, số lượng | Giữ chỗ trùng, số lượng âm hoặc dữ liệu cũ |
| Đơn hàng → Thanh toán | Mã đơn, số tiền, đơn vị tiền, phương thức | Sai số tiền, giao dịch trùng hoặc trạng thái không rõ |
| Thanh toán → Broker | Sự kiện thanh toán thành công hoặc thất bại | Sự kiện bị mất, lặp hoặc đến muộn |
| Broker → Đơn hàng | Cập nhật trạng thái theo sự kiện | Xử lý lặp hoặc sai thứ tự làm trạng thái bị ghi đè |
| Đơn hàng → Thông báo | Yêu cầu gửi xác nhận | Gửi trùng, gửi sai nội dung hoặc không gửi được |
| Dịch vụ → Cơ sở dữ liệu | Ghi đơn, giao dịch và trạng thái | Ghi một phần, deadlock hoặc dữ liệu không nhất quán |

### Phân công kiểm chứng

| Điểm tích hợp | Kiểm thử chính | Nhóm chịu trách nhiệm chính | Phối hợp |
|---|---|---|---|
| Đơn hàng → Tồn kho | Hợp đồng và tích hợp giữ chỗ, hết hàng, yêu cầu lặp | Nhóm đơn hàng và tồn kho | Nhóm tích hợp |
| Đơn hàng → Thanh toán | Hợp đồng số tiền, timeout, retry và trạng thái giao dịch | Nhóm đơn hàng và thanh toán | Nhóm tích hợp, bảo mật |
| Thanh toán → Broker | Kiểm tra phát sự kiện, định danh và xác nhận | Nhóm thanh toán | Nhóm nền tảng |
| Broker → Đơn hàng | Kiểm thử consumer với sự kiện lặp, trễ và sai thứ tự | Nhóm đơn hàng | Nhóm nền tảng, thanh toán |
| Đơn hàng → Thông báo | Kiểm thử yêu cầu gửi, lỗi nhà cung cấp và retry | Nhóm đơn hàng và thông báo | Nhóm tích hợp |
| Dịch vụ → Cơ sở dữ liệu | Kiểm thử transaction, migration và tính nhất quán | Nhóm sở hữu từng dịch vụ | Nhóm dữ liệu hoặc nền tảng |

### Bằng chứng và điều kiện hoàn tất

Với từng điểm, nhóm cần lưu:

- Hợp đồng hoặc schema được kiểm thử.
- Kịch bản và dữ liệu dùng để kiểm tra.
- Kết quả chạy và phiên bản thành phần.
- Chủ sở hữu và nơi báo lỗi.
- Giới hạn còn lại hoặc phụ thuộc chưa kiểm soát.

Luồng chỉ nên được xem là có bằng chứng đầy đủ khi các điểm tích hợp trọng yếu có kiểm thử phù hợp và một số kiểm thử đầu cuối xác nhận hành trình. Ví dụ, kiểm thử từng dịch vụ thành công chưa chứng minh rằng một đơn hàng không bị ghi nhận hai lần khi broker phát lại sự kiện.

## 9. Xử lý lỗi phát hiện tại ranh giới tích hợp

Khi kiểm thử thất bại, nguyên nhân có thể nằm ở provider, consumer, hợp đồng, môi trường hoặc dữ liệu. Cần có quy trình điều tra chung để tránh tranh luận về quyền sở hữu trước khi xác định bằng chứng.

Một cách tiếp cận:

1. Lưu request, response hoặc thông điệp đã trao đổi, cùng correlation ID và thời điểm.
2. Xác nhận phiên bản provider, consumer, schema và cấu hình môi trường.
3. Kiểm tra dữ liệu đầu vào, trạng thái ban đầu và kết quả ở mỗi phía.
4. Xác định thành phần đầu tiên có hành vi khác hợp đồng.
5. Tái hiện lỗi bằng môi trường hoặc dữ liệu có thể kiểm soát.
6. Giao phần sửa cho nhóm sở hữu thành phần hoặc hợp đồng bị vi phạm.
7. Yêu cầu các nhóm liên quan cập nhật kiểm thử của họ.
8. Chạy lại kiểm thử tại ranh giới và các luồng bị ảnh hưởng.

Không nên mặc định nhóm phát hiện lỗi là nhóm phải sửa. Người phát hiện cung cấp bằng chứng và hỗ trợ điều tra; nhóm sở hữu thành phần chịu trách nhiệm sửa phần của mình; đầu mối tích hợp điều phối việc xác nhận toàn bộ tương tác.

### Khi chưa xác định được nguyên nhân

Nếu chưa rõ lỗi nằm ở phía nào, chủ sở hữu luồng hoặc tích hợp cần tiếp nhận điều phối. Có thể lập một phiên điều tra chung với provider, consumer và nền tảng. Trong thời gian đó, ghi trạng thái “đang điều tra”, người phụ trách và bằng chứng còn thiếu.

Không nên đóng lỗi bằng cách chuyển qua lại giữa các nhóm hoặc tạm tắt kiểm thử. Nếu cần giảm ảnh hưởng để tiếp tục công việc, phải ghi nhận biện pháp tạm thời và rủi ro còn lại.

## 10. Những sai lầm thường gặp khi phân công

- **Cho rằng provider kiểm tra là đủ:** consumer có thể diễn giải hợp đồng sai hoặc xử lý lỗi không đúng.
- **Cho rằng consumer phải tự thích nghi với mọi thay đổi:** provider vẫn chịu trách nhiệm công bố và duy trì hợp đồng.
- **Không có đầu mối cho tích hợp xuyên nhóm:** các phần việc riêng lẻ có thể hoàn tất nhưng không ai xác nhận toàn bộ tương tác.
- **Giao mọi kiểm thử cho nhóm QA:** nhóm sở hữu mã nguồn và hợp đồng không tham gia duy trì bằng chứng.
- **Chỉ định người viết nhưng không chỉ định người duy trì:** kiểm thử nhanh chóng lỗi thời khi giao diện hoặc dữ liệu thay đổi.
- **Không kiểm tra điều kiện lỗi:** chỉ thử phản hồi thành công, bỏ qua timeout, retry, gửi lặp và xử lý một phần.
- **Dùng mock thay cho mọi kiểm tra tích hợp:** mock xác minh giả định của một phía nhưng không chứng minh hệ thống thật tương thích.
- **Không lưu correlation ID và bằng chứng:** lỗi xuyên dịch vụ khó điều tra và khó tái hiện.
- **Không xem xét cấu hình triển khai:** kiểm thử ở môi trường phát triển đạt nhưng kết nối thật có thể thất bại.
- **Không cập nhật trách nhiệm khi kiến trúc thay đổi:** nhóm hoặc dịch vụ mới xuất hiện nhưng ma trận vẫn phản ánh cấu trúc cũ.

## 11. Mẫu ghi nhận trách nhiệm tại điểm tích hợp

Có thể dùng mẫu sau cho mỗi ranh giới:

~~~text
ĐIỂM TÍCH HỢP:
Mục tiêu nghiệp vụ:

PROVIDER:
Thành phần / nhóm sở hữu:
Hợp đồng được công bố:
Kiểm thử phía provider:

CONSUMER:
Thành phần / nhóm sở hữu:
Kỳ vọng khi sử dụng:
Kiểm thử phía consumer:

RỦI RO:
Tình huống lỗi:
Hậu quả:
Điều kiện xuất hiện:

KIỂM CHỨNG:
Tầng chính:
Tầng bổ trợ:
Kịch bản và dữ liệu:
Điều kiện đạt:
Nơi lưu bằng chứng:

TRÁCH NHIỆM:
Người/nhóm viết:
Người/nhóm duy trì:
Người/nhóm thực thi:
Đầu mối điều phối:
Người xử lý lỗi:

VẬN HÀNH:
Log / metric / trace:
Cảnh báo:
Cách phục hồi hoặc đối soát:

TRẠNG THÁI:
Rủi ro còn lại:
Hành động tiếp theo:
Thời điểm xem xét lại:
~~~

Mẫu này cần được điền ở mức vừa đủ cho từng điểm. Không nên tạo tài liệu nặng nề cho mọi lời gọi nội bộ đơn giản; hãy tập trung vào những ranh giới có rủi ro, phụ thuộc hoặc trách nhiệm liên nhóm đáng kể.

## Kết luận

Phân công trách nhiệm kiểm tra lỗi tại từng điểm tích hợp giúp bảo đảm các ranh giới giữa thành phần không trở thành vùng mù chất lượng. Provider chịu trách nhiệm về hợp đồng và hành vi cung cấp; consumer chịu trách nhiệm về cách sử dụng và xử lý phản hồi; nhóm nền tảng và vận hành chịu trách nhiệm về hạ tầng và khả năng quan sát; chủ sở hữu luồng hoặc tích hợp điều phối bằng chứng xuyên nhóm.

Khi mỗi điểm tích hợp có hợp đồng rõ, phép kiểm chứng phù hợp, người duy trì, đầu mối xử lý lỗi và bằng chứng truy vết được, nhóm có thể phát hiện vấn đề sớm và điều tra nhanh hơn. Việc phân công cần được xem xét lại mỗi khi thêm dịch vụ, thay đổi giao thức, chuyển quyền sở hữu hoặc xuất hiện sự cố cho thấy ranh giới hiện tại chưa được kiểm tra đầy đủ.
