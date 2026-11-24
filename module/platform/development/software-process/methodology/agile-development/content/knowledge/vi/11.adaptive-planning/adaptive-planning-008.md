# Xử lý phụ thuộc mà vẫn bảo toàn khả năng đổi hướng

## 1. Vấn đề cốt lõi của lập kế hoạch thích ứng

Trong phát triển phần mềm theo **Agile**, nhóm cần lập kế hoạch đủ rõ để phối hợp và bàn giao giá trị, nhưng cũng phải có khả năng điều chỉnh khi phản hồi người dùng, điều kiện kỹ thuật hoặc ưu tiên kinh doanh thay đổi. Điều đó trở nên khó khăn khi một công việc chỉ có thể hoàn thành nếu một công việc, hệ thống hoặc quyết định khác đã sẵn sàng.

Ví dụ, nhóm phát triển chức năng thanh toán trực tuyến cho ứng dụng bán hàng cần tích hợp với cổng thanh toán, biết trạng thái tồn kho và làm rõ chính sách xử lý giao dịch thất bại. Nếu một dịch vụ bên ngoài chưa sẵn sàng, nhóm có thể bị chặn dù phần mã của mình đã hoàn thành. Nếu nhóm vội cam kết toàn bộ chức năng cho một ngày cố định, mọi thay đổi ở cổng thanh toán có nguy cơ kéo theo trì hoãn dây chuyền.

**Phụ thuộc (dependency)** là mối quan hệ trong đó khả năng bắt đầu, tiến hành, kiểm tra hoặc hoàn thành một công việc chịu ảnh hưởng bởi một đầu vào, kết quả hoặc quyết định khác. Phụ thuộc không mặc nhiên là xấu: hệ thống phần mềm cần cộng tác và tích hợp. Vấn đề là **phụ thuộc không được nhìn thấy, không có người điều phối hoặc bị biến thành cam kết cứng khi mức bất định còn cao**.

Bài học này thuộc chủ đề **Kế hoạch thích ứng** của module **AGILE_DEVELOPMENT**. Mục tiêu là dùng phản hồi sớm, chia nhỏ việc và cải tiến dòng công việc để **xử lý phụ thuộc mà không đánh mất lựa chọn thay đổi ưu tiên hoặc giải pháp**. Không phải cứ loại bỏ mọi phụ thuộc mới là Agile; cần hiểu phụ thuộc nào bắt buộc, phụ thuộc nào có thể giảm và cách quản lý những phụ thuộc còn lại.

### Kết quả học tập

Sau bài học, người học có thể:

1. Phân loại phụ thuộc giữa hạng mục, nhóm, kỹ thuật, hệ thống ngoài và quyết định nghiệp vụ.
2. Vẽ bản đồ phụ thuộc, phân biệt đường đi cần thiết với giả định có thể thay đổi.
3. Chọn cách giảm hoặc quản lý phụ thuộc: chia lát giá trị, hợp đồng giao tiếp, mock/stub, kiểm thử hợp đồng, feature flag, quyết định theo thời điểm phù hợp.
4. Lập kế hoạch theo nhiều mức thời gian, kèm rủi ro, tín hiệu cảnh báo, người phụ trách và phương án dự phòng.
5. Ứng dụng cách phối hợp phù hợp với Scrum, Kanban và các thực hành XP, đồng thời đo tác động lên dòng công việc.

## 2. Nhận diện các loại phụ thuộc

Không nên gom mọi nguyên nhân chờ đợi vào một nhãn “bị phụ thuộc”. Cách xử lý phụ thuộc kỹ thuật khác với phụ thuộc vào phê duyệt pháp lý hay quyết định ưu tiên.

| Loại phụ thuộc | Dấu hiệu điển hình | Ví dụ | Hướng xử lý thường phù hợp |
|---|---|---|---|
| **Thứ tự công việc** | Hạng mục B cần đầu ra của A. | Muốn đối soát hoàn tiền phải có sự kiện hoàn tiền được ghi nhận. | Xem có thể chia nhỏ, đảo thứ tự hoặc thực hiện một phần độc lập không. |
| **Dữ liệu** | Chưa có hoặc chưa rõ cấu trúc, chất lượng dữ liệu. | Không biết trạng thái tồn kho cập nhật theo quy tắc nào. | Thống nhất hợp đồng dữ liệu, dùng mẫu đại diện, kiểm tra dữ liệu sớm. |
| **Tích hợp kỹ thuật** | Cần API, hệ thống hoặc môi trường khác. | Cổng thanh toán chưa cung cấp sandbox ổn định. | Xác minh hợp đồng, dùng mô phỏng có giới hạn, kiểm thử tích hợp thật sớm. |
| **Giữa nhóm** | Cần người của nhóm khác phát triển hoặc phê duyệt. | Nhóm thanh toán cần đội nền tảng mở quyền truy cập. | Thống nhất đầu ra, người phụ trách, thời điểm cần, ưu tiên chung. |
| **Năng lực/chuyên môn** | Một người hoặc kỹ năng hiếm là nút thắt. | Chỉ một kỹ sư biết hệ thống đối soát cũ. | Chia sẻ tri thức, làm cặp, xoay vòng công việc, chuẩn bị hỗ trợ. |
| **Nghiệp vụ/quyết định** | Quy tắc hoặc người có thẩm quyền chưa xác nhận. | Chưa chốt khi nào giữ tiền và khi nào hoàn tiền. | Nêu rõ các phương án, tác động và người ra quyết định. |
| **Nhà cung cấp/bên ngoài** | Thời điểm hoặc chất lượng đầu ra ngoài kiểm soát trực tiếp. | Đối tác xác thực tài khoản chưa có ngày bàn giao chắc chắn. | Theo dõi cam kết và bằng chứng, thương lượng giao theo phần, chuẩn bị fallback. |
| **Tuân thủ và vận hành** | Cần kiểm định, đánh giá bảo mật hoặc sẵn sàng phát hành. | Quy trình lưu vết giao dịch cần được kiểm tra trước khi mở rộng. | Đưa kiểm soát vào sớm, định nghĩa tiêu chuẩn, không coi an toàn là việc cuối. |

Một hạng mục có thể có **nhiều loại phụ thuộc đồng thời**. Ví dụ tích hợp thanh toán vừa cần tài liệu API, quyền truy cập sandbox, người nghiệp vụ chốt quy tắc hoàn tiền và đội bảo mật xem xét cách lưu dữ liệu. Vì thế, chỉ ghi “blocked by payment API” có thể chưa đủ để nhóm hành động.

### 2.1. Phụ thuộc bắt buộc và phụ thuộc do cách tổ chức tạo ra

Nên phân biệt hai nhóm nguyên nhân:

- **Bắt buộc về nghiệp vụ hoặc kỹ thuật:** không được xác nhận thanh toán khi hệ thống chưa có thông tin đáng tin về giao dịch; không được phát hành khi chưa đáp ứng nghĩa vụ an toàn bắt buộc.
- **Phát sinh từ thiết kế hoặc quy trình hiện tại:** mọi thay đổi giao diện phải chờ nhóm API hoàn tất cả một phân hệ; mọi quyết định phải qua nhiều cấp duyệt dù chỉ ảnh hưởng một chức năng nhỏ.

Loại thứ nhất cần quản lý cẩn thận; loại thứ hai thường có cơ hội **thiết kế lại cách phối hợp, chia việc hoặc phân quyền quyết định**. Trước khi chấp nhận một phụ thuộc là bất biến, nhóm nên hỏi: “Điều gì thực sự phải có trước?”, “Có phần nào có thể thử nghiệm an toàn trước?”, “Ai cần quyết định và vì sao?”.

### 2.2. Phụ thuộc không đồng nghĩa với blocker

**Dependency** là quan hệ ảnh hưởng; **blocker** là trở ngại đang làm công việc không thể tiến theo kế hoạch hiện tại. Một dịch vụ ngoài chưa bàn giao có thể là phụ thuộc được biết trước nhưng chưa chặn công việc nếu nhóm vẫn đang làm phần giao diện và kiểm thử hợp đồng. Khi đến bước tích hợp thật mà dịch vụ vẫn chưa sẵn sàng, phụ thuộc đó trở thành blocker.

Phân biệt này giúp nhóm hành động sớm. Chờ đến khi công việc bị chặn mới ghi nhận phụ thuộc thường là quá muộn để đổi hướng với chi phí thấp.

## 3. Mô hình hóa phụ thuộc thay vì chỉ ghi trong đầu

Bản đồ phụ thuộc (dependency map) giúp nhóm nhìn thấy các quan hệ quan trọng, đường đi tạo ra giá trị và những điểm có thể thay thế. Không cần một sơ đồ phức tạp cho mọi story; chỉ nên trực quan hóa đủ để hỗ trợ quyết định.

Giả sử mục tiêu là **khách có thể đặt một đơn hàng và thanh toán bằng một phương thức trực tuyến**. Các hạng mục minh họa:

| Mã | Đầu ra | Quan hệ quan trọng |
|---|---|---|
| A | Xem tổng tiền và xác nhận đơn | Cần quy tắc tính tổng tiền đã rõ. |
| B | Tạo đơn ở trạng thái chờ thanh toán | Cần quy tắc đặt hàng và dữ liệu sản phẩm tối thiểu. |
| C | Tạo yêu cầu thanh toán với đối tác | Cần hợp đồng API và quyền truy cập sandbox. |
| D | Nhận, xác minh kết quả thanh toán | Cần các kịch bản trạng thái và cơ chế chống xử lý lặp. |
| E | Hiển thị trạng thái đơn và thông báo cho khách | Cần trạng thái giao dịch đáng tin cậy; giao diện có thể được thử trước với dữ liệu mô phỏng. |
| F | Phát hành giới hạn cho nhóm người dùng đầu tiên | Cần luồng A–E đạt tiêu chí chất lượng và kiểm soát rủi ro cần thiết. |

~~~mermaid
flowchart LR
    A["A: Tổng tiền"] --> B["B: Tạo đơn"]
    B --> C["C: Khởi tạo thanh toán"]
    C --> D["D: Xác minh kết quả"]
    D --> F["F: Phát hành giới hạn"]
    B --> E["E: Trạng thái đơn"]
    D --> E
    E --> F
    X["Hợp đồng API và sandbox"] -.-> C
    Y["Quy tắc xử lý giao dịch"] -.-> D
    Z["Kiểm soát bảo mật và vận hành"] -.-> F
~~~

**Ý nghĩa của sơ đồ:** nhóm có thể phát triển bản xem tổng tiền, tạo đơn và thử giao diện trạng thái trước khi tích hợp thật. Nhưng **không được coi thanh toán đã thành công chỉ vì mock trả về thành công**. Đường dẫn tới phát hành nhận tiền thật vẫn cần kết quả tích hợp và kiểm soát an toàn.

### 3.1. Cách ghi một phụ thuộc có thể hành động

Một bản ghi hữu ích cần nhiều hơn “chờ nhóm khác”:

~~~text
ID: DEP-PAY-01
Hạng mục cần đầu vào: D - Xác minh kết quả thanh toán
Nguồn phụ thuộc: Đội tích hợp cổng thanh toán
Đầu ra cần nhận: Hợp đồng callback, chữ ký xác thực, ví dụ giao dịch lỗi/lặp
Người điều phối: Đại diện nhóm phát triển sản phẩm
Người/nhóm cung cấp: Nhóm tích hợp thanh toán
Ngày cần để giữ mốc hiện tại: Mốc đã thỏa thuận trong kế hoạch
Trạng thái: Đang làm rõ; chưa có bằng chứng tích hợp thật
Rủi ro: Không xác minh được giao dịch hoặc ghi nhận trạng thái sai
Việc có thể làm trong lúc chờ: Thiết kế bộ trạng thái và contract tests
Tín hiệu cần đổi kế hoạch: API không ổn định trước thời điểm tích hợp đã thống nhất
Phương án thay thế: Chỉ phát hành luồng tạo đơn chờ thanh toán, chưa nhận tiền thật
~~~

Mốc thời gian trong bản ghi là **mốc điều phối và tín hiệu ra quyết định**, không phải lời khẳng định rằng nhà cung cấp chắc chắn giao đúng ngày. Nếu thời điểm chưa đáng tin, nhóm phải ghi rõ mức bất định.

### 3.2. Đừng nhầm sơ đồ phụ thuộc với sơ đồ phân công

“Nhóm Frontend làm A, nhóm Backend làm B” chưa cho biết **kết quả nào chặn kết quả nào**. Thực tế, hai nhóm có thể làm song song nếu đã thống nhất hợp đồng API. Ngược lại, hai công việc trong cùng một nhóm vẫn có thể phụ thuộc nghiêm trọng nếu chia theo lớp kỹ thuật không tạo được phần mềm có thể kiểm chứng.

Nên vẽ quan hệ giữa **đầu ra và điều kiện cần**, không chỉ nối tên nhóm bằng mũi tên.

## 4. Tác động của phụ thuộc lên kế hoạch và khả năng đổi hướng

Phụ thuộc không được quản lý thường gây bốn hệ quả:

1. **Tăng thời gian chờ:** công việc dừng lại dù người thực hiện sẵn sàng.
2. **Tăng WIP và chuyển ngữ cảnh:** thay vì hoàn thành việc đang làm, các thành viên bắt đầu nhiều việc khác.
3. **Dồn tích hợp về cuối:** các phần được phát triển riêng nhưng chỉ phát hiện sai lệch khi kết nối thật.
4. **Giảm lựa chọn thay đổi:** kế hoạch đã dựa vào một công nghệ, một nhà cung cấp hoặc một mốc bàn giao quá sớm, khiến việc điều chỉnh trở nên đắt đỏ.

### 4.1. Độ bất định lan truyền

Nếu chức năng B chỉ bắt đầu được sau A, chức năng C chỉ hoàn thành khi B ổn định, một thay đổi ở A có thể tác động toàn bộ chuỗi. Đây là lý do nhóm cần xem **đường phụ thuộc có rủi ro cao**, không chỉ ước lượng từng story riêng lẻ.

Không nên tính ngày giao cuối cùng bằng cách cộng tất cả ước lượng rồi coi đó là cam kết chắc chắn. Cần xét công việc có thể làm song song, thời gian chờ, mức dao động, sự cố và những giả định có thể không đúng.

### 4.2. Đường găng hữu ích nhưng không đủ

Trong kế hoạch có quan hệ trước–sau, khái niệm **critical path (đường găng)** giúp xác định chuỗi công việc có thể quyết định thời điểm hoàn thành một mục tiêu với các giả định hiện tại. Tuy nhiên, phát triển phần mềm có nhiều thay đổi về phạm vi, độ khó và phản hồi. Vì vậy, đường găng là **ảnh chụp dự báo tại một thời điểm**, không phải lý do khóa mọi quyết định kiến trúc hoặc ưu tiên.

Khi phụ thuộc hoặc giá trị thay đổi, nhóm phải tính lại kế hoạch hoặc chọn mục tiêu nhỏ hơn có thể mang lại giá trị sớm hơn.

### 4.3. Chi phí trì hoãn và chi phí cam kết sớm

Hai loại chi phí cần xem cùng lúc:

- **Chi phí trì hoãn:** nếu chờ quá lâu, người dùng không nhận được giá trị, cơ hội kinh doanh mất đi hoặc rủi ro vận hành tiếp tục tồn tại.
- **Chi phí cam kết sớm:** nếu chốt công nghệ, hợp đồng tích hợp hoặc phạm vi khi còn ít bằng chứng, thay đổi sau đó có thể rất tốn kém.

Lập kế hoạch thích ứng tìm sự cân bằng: **quyết định sớm những điều bắt buộc hoặc có rủi ro lớn**, giữ mở những lựa chọn chưa cần chốt và thường xuyên cập nhật dự báo khi có thông tin mới.

## 5. Kế hoạch nhiều mức thời gian: rõ việc gần, mở việc xa

**Rolling-wave planning (lập kế hoạch cuốn chiếu)** là cách lập kế hoạch chi tiết hơn cho phần việc gần, còn phần việc xa duy trì ở mức mục tiêu, lựa chọn và giả định cho đến khi có thêm thông tin. Trong Agile, cách tư duy này phù hợp với việc ưu tiên backlog và lặp lại vòng phản hồi.

| Mức | Cần rõ đến đâu? | Cách phản ánh phụ thuộc |
|---|---|---|
| **Tầm nhìn / mục tiêu sản phẩm** | Nhóm người dùng, vấn đề, outcome và ràng buộc lớn. | Phụ thuộc chiến lược, nghĩa vụ bắt buộc, đối tác và năng lực chính. |
| **Kế hoạch phát hành / giai đoạn** | Các khả năng dự kiến, chuỗi giá trị, phạm vi tối thiểu và lựa chọn thay thế. | Các mốc tích hợp, rủi ro, nhóm cung cấp đầu vào, điều kiện thay đổi kế hoạch. |
| **Những tuần hoặc Sprint gần** | Hạng mục đủ nhỏ, ví dụ, tiêu chí chấp nhận, năng lực và thứ tự. | Đầu vào cần ngay, môi trường kiểm thử, người trả lời, blocker thực tế. |
| **Hằng ngày** | Công việc nào đang tiến, bị chặn, cần phối hợp. | Xử lý blocker, hỗ trợ nhau hoàn thành trước khi mở thêm việc. |

Một roadmap thích ứng nên truyền đạt **hướng đi, thứ tự tương đối, mức tin cậy và điều kiện thay đổi**, thay vì trình bày mọi tính năng tương lai như một hợp đồng ngày-tháng bất biến.

### 5.1. Ghi dự báo cùng giả định

Thay vì:

> “Ngày 15 phải hoàn thành thanh toán, dù đối tác chưa cung cấp sandbox.”

Nhóm có thể diễn đạt:

> “Mục tiêu là thử nghiệm thanh toán ở phạm vi giới hạn khi hợp đồng API, kiểm tra tích hợp và quy trình xử lý lỗi đã được xác nhận. Nếu sandbox chưa sẵn sàng trước mốc kiểm tra đã thống nhất, nhóm sẽ chuyển sang hoàn thành luồng đặt đơn chờ thanh toán và cập nhật thời điểm thử thanh toán thật.”

Cách diễn đạt thứ hai **không phải né cam kết**: nó làm rõ kết quả mục tiêu, điều kiện, rủi ro và hành động khi giả định sai. Với thời hạn pháp lý hoặc cam kết bên ngoài không thể đổi, nhóm càng phải làm rõ sớm phần giá trị bắt buộc và phương án giảm phạm vi được phép, không được hy sinh kiểm soát thiết yếu.

## 6. Giảm phụ thuộc bằng cách chia nhỏ theo lát giá trị

Một nguồn phụ thuộc phổ biến là chia backlog theo tầng kỹ thuật: “xây toàn bộ database”, “xây toàn bộ API”, rồi “xây toàn bộ giao diện”. Cách này có thể khiến mọi phần phải chờ nhau và chỉ nhận được phản hồi của người dùng rất muộn.

**Chia lát dọc (vertical slicing)** nhằm tạo một đường đi xuyên qua những thành phần cần thiết cho một kết quả người dùng, dù phạm vi ban đầu còn nhỏ. Chẳng hạn:

| Cách chia theo bộ phận | Cách chia theo lát giá trị |
|---|---|
| Sprint 1: toàn bộ schema đơn hàng | Lát 1: khách thấy tổng tiền và tạo được một đơn chờ thanh toán hợp lệ. |
| Sprint 2: toàn bộ API thanh toán | Lát 2: khách được dẫn tới một phương thức thanh toán hỗ trợ trong phạm vi thử nghiệm. |
| Sprint 3: giao diện, báo cáo và thông báo | Lát 3: khách thấy trạng thái giao dịch được xác minh, kể cả thất bại hoặc đang xử lý. |
| Sprint 4: tích hợp và kiểm thử | Mỗi lát đều được tích hợp và kiểm tra sớm, chỉ mở cho người dùng thật khi đạt yêu cầu an toàn. |

Chia lát không có nghĩa bỏ qua thiết kế kiến trúc hoặc ép mọi thứ thành một tính năng dùng được trong vài giờ. Đôi khi cần một spike, cải tiến nền tảng hoặc chuẩn bị bảo mật trước. Điều quan trọng là **giảm thời gian giữa lúc đặt giả thuyết và lúc có thể kiểm tra kết quả**.

### 6.1. Các cách chia lát hữu ích

- **Theo trường hợp nghiệp vụ:** đơn trả tiền khi nhận hàng trước, rồi đến thanh toán qua một cổng tích hợp.
- **Theo nhóm người dùng:** thử với nhân viên nội bộ hoặc nhóm khách hàng thí điểm có kiểm soát trước khi mở rộng.
- **Theo biến thể quy tắc:** xử lý một loại hoàn tiền trước, rồi thêm trường hợp phức tạp hơn.
- **Theo hành trình:** đầu tiên xem trạng thái, sau đó nhận thông báo, rồi bổ sung thay đổi hoặc hủy.
- **Theo rủi ro:** kiểm tra trước luồng có nguy cơ sai tiền, sai quyền truy cập hoặc dữ liệu không nhất quán.

Mỗi lát cần được kiểm tra xem **có giá trị hoặc giảm bất định rõ ràng**, và có đạt tiêu chuẩn hoàn thành tương ứng hay không. Một màn hình giả lập giao dịch thành công không phải thanh toán thật đã hoàn tất.

## 7. Giảm phụ thuộc tích hợp mà không tạo cảm giác an toàn giả

Phụ thuộc vào API, hệ thống cũ hoặc nhà cung cấp bên ngoài thường không thể xóa hoàn toàn. Nhóm có thể giảm thời gian chờ và phát hiện rủi ro bằng những kỹ thuật dưới đây.

### 7.1. Thống nhất hợp đồng giao tiếp sớm

**API contract** làm rõ yêu cầu, phản hồi, mã lỗi, định dạng dữ liệu, quyền truy cập và cách thay đổi phiên bản. Hai nhóm có thể đồng thuận về hợp đồng rồi làm việc song song, thay vì chờ một bên hoàn thành toàn bộ chức năng.

Ví dụ với dịch vụ xác nhận thanh toán, cần làm rõ:

- Mã giao dịch và mã đơn liên kết thế nào?
- Những trạng thái nào có thể xảy ra: chờ xử lý, thành công, thất bại, hoàn tiền?
- Một callback có thể được gửi lặp hoặc đến sai thứ tự không?
- Cách xác minh nguồn callback và chống giả mạo là gì?
- Khi lỗi mạng xảy ra, hai phía khôi phục trạng thái nhất quán bằng cách nào?

Chỉ có tài liệu trường dữ liệu chưa đủ; **hành vi và trường hợp lỗi** cũng là một phần quan trọng của hợp đồng.

### 7.2. Mock và stub để phát triển song song

**Mock/stub** có thể tạo phản hồi mô phỏng từ hệ thống chưa sẵn sàng, giúp nhóm phát triển giao diện, kiểm thử quy tắc và chuẩn bị tình huống lỗi. Ví dụ, khi đối tác chưa cấp sandbox, nhóm có thể mô phỏng phản hồi “đang xử lý”, “thất bại” và “thành công” để kiểm tra luồng hiển thị.

Tuy nhiên:

> **Mô phỏng giúp giảm thời gian chờ nhưng không chứng minh tích hợp thật hoạt động.**

Nhóm phải lên kế hoạch kiểm thử với dịch vụ thật hoặc môi trường tích hợp đáng tin, đặc biệt cho xác thực, idempotency, giao dịch lỗi và khôi phục. Cần quản lý sự lệch giữa mock và hợp đồng thật.

### 7.3. Kiểm thử hợp đồng và tích hợp liên tục

**Contract testing** hỗ trợ kiểm tra các bên có tuân theo những kỳ vọng giao tiếp đã thống nhất hay không. **Continuous Integration (CI)** giúp kiểm tra mã được tích hợp thường xuyên để phát hiện lỗi sớm.

Khi có điều kiện, nhóm nên:

1. Chốt kỳ vọng API tối thiểu cho lát công việc gần nhất.
2. Kiểm tra cả trường hợp thành công và thất bại.
3. Cập nhật test khi hợp đồng thay đổi; thông báo bên liên quan về phiên bản.
4. Chạy kiểm thử tích hợp thật theo nhịp phù hợp, không dồn đến ngày phát hành.
5. Giám sát kết quả sau triển khai để phát hiện sai lệch mà môi trường thử không thể mô phỏng.

Không phải mọi hệ thống cần cùng một bộ công cụ; chọn thực hành theo nguy cơ và năng lực hiện tại.

### 7.4. Feature flag và khả năng phát hành từng phần

**Feature flag** cho phép triển khai mã mới trong khi chỉ mở hành vi cho một phạm vi được kiểm soát. Ví dụ, phần giao diện thanh toán mới có thể được triển khai nhưng chưa bật cho khách hàng cho tới khi xác minh tích hợp thật và điều kiện bảo mật.

Flag giúp **tách thời điểm triển khai kỹ thuật khỏi thời điểm bật tính năng**, qua đó giữ lựa chọn phát hành theo từng bước. Dù vậy, flag mang theo chi phí quản lý trạng thái, kiểm thử các tổ hợp, xóa flag cũ và quan sát sau bật. Nó không được dùng để đi vòng những kiểm soát cần thiết cho tiền bạc, dữ liệu hoặc an toàn.

### 7.5. Trì hoãn quyết định khó đảo ngược, nhưng không trì hoãn việc học

Một quyết định công nghệ khó đảo ngược có thể được giữ mở đến khi nhóm thu được đủ bằng chứng. Song **hoãn cam kết không đồng nghĩa hoãn tìm hiểu**. Với lựa chọn nhà cung cấp thanh toán, nhóm có thể sớm đánh giá hợp đồng, mức hỗ trợ hoàn tiền, rủi ro vận hành và chi phí trước khi ký cam kết dài hạn.

Nếu xây một lớp trừu tượng giúp thay nhà cung cấp dễ hơn với chi phí chấp nhận được, đó có thể là khoản đầu tư hợp lý. Nếu cố tạo một nền tảng hỗ trợ hàng chục nhà cung cấp chưa từng được yêu cầu, nhóm lại có nguy cơ **thiết kế quá mức** và chậm nhận phản hồi.

## 8. Giảm phụ thuộc giữa nhóm và phụ thuộc vào quyết định

Kỹ thuật tốt chưa đủ nếu mọi vấn đề vẫn phải qua nhiều hàng chờ tổ chức. Phụ thuộc giữa nhóm cần có **đầu ra cụ thể, người điều phối và ưu tiên tương thích**.

### 8.1. Lập cam kết theo đầu ra, không chỉ theo ngày

Thay vì yêu cầu “nhóm nền tảng xong phần thanh toán trong Sprint tới”, hãy thỏa thuận:

- API hoặc đầu ra cụ thể nào phải có?
- Mẫu giao dịch và kịch bản lỗi tối thiểu là gì?
- Có thể giao từng phần nào trước để nhóm tiêu thụ bắt đầu kiểm tra?
- Ai xác nhận kết quả đạt yêu cầu?
- Tín hiệu nào cho thấy thời điểm hoặc nội dung thỏa thuận phải thay đổi?

Một cuộc trao đổi ngắn giữa nhóm cung cấp và nhóm tiêu thụ thường có giá trị hơn việc mỗi nhóm tự lên lịch rồi hy vọng các mốc khớp nhau.

### 8.2. Gỡ nút thắt chuyên môn

Khi chỉ một kỹ sư hiểu hệ thống cũ, mọi hạng mục liên quan dễ chờ người đó. Nhóm có thể:

- Làm cặp ở hạng mục rủi ro cao để chia sẻ kiến thức.
- Ghi quyết định và quy trình vận hành tối thiểu, dễ tìm.
- Đưa người thứ hai tham gia kiểm thử và điều tra sự cố.
- Tách việc chuẩn bị dữ liệu, kiểm tra hợp đồng hoặc tài liệu để người khác hỗ trợ.
- Tránh xếp nhiều yêu cầu có hạn chót trùng nhau vào cùng một chuyên gia.

Các biện pháp ban đầu có thể tốn thêm thời gian nhưng giảm rủi ro phụ thuộc dài hạn.

### 8.3. Có đường ra quyết định minh bạch

Một phụ thuộc nghiệp vụ thường bị mô tả là “chờ xác nhận” mà không ai biết cần xác nhận **điều gì**. Nhóm nên ghi:

| Thông tin | Ví dụ |
|---|---|
| Câu hỏi cần quyết định | Có giữ đơn trong bao lâu khi thanh toán đang chờ? |
| Lựa chọn hiện có | Giữ chỗ trong giới hạn ngắn; không giữ chỗ; hoặc chỉ giữ khi có trạng thái xác minh. |
| Tác động của từng lựa chọn | Trải nghiệm người dùng, nguy cơ hết hàng, độ phức tạp và số trường hợp ngoại lệ. |
| Người có thẩm quyền | Product Owner và đại diện vận hành kho theo phạm vi trách nhiệm. |
| Mốc cần trả lời | Trước khi hoàn thiện quy tắc giữ tồn kho cho lát thanh toán đầu tiên. |
| Xử lý tạm | Không tự giả định thời hạn giữ tồn; tiếp tục làm các phần không phụ thuộc quyết định này. |

Việc làm rõ **quyền quyết định** giúp tránh cả hai cực đoan: thành viên tự ý đặt chính sách nghiệp vụ hoặc không ai dám quyết định dù thông tin đã đủ.

## 9. Quản lý rủi ro phụ thuộc: khi nào cần đổi kế hoạch?

Một kế hoạch thích ứng không chỉ liệt kê phụ thuộc mà còn có **ngưỡng và tín hiệu cần hành động**. Nếu không có điều kiện đổi hướng, bảng rủi ro dễ trở thành danh sách đọc cho biết.

| Rủi ro | Dấu hiệu sớm | Giảm nguy cơ | Phương án khi xảy ra |
|---|---|---|---|
| Sandbox thanh toán chậm bàn giao | Chưa có tài khoản hoặc phản hồi thử tại mốc chuẩn bị tích hợp. | Yêu cầu đầu ra tối thiểu, làm contract tests, kiểm tra tiến độ thường xuyên. | Giao luồng đặt đơn chờ thanh toán; chưa mở giao dịch thật. |
| Quy tắc hoàn tiền chưa rõ | Nghiệp vụ đưa câu trả lời khác nhau cho cùng ví dụ. | Dùng bảng ví dụ và người quyết định rõ ràng. | Chưa triển khai hoàn tiền phức tạp; giữ phạm vi đã xác nhận. |
| API thay đổi không tương thích | Schema hoặc mã lỗi không khớp hợp đồng đã thống nhất. | Kiểm thử hợp đồng và quản lý phiên bản. | Lùi tích hợp phần bị ảnh hưởng hoặc dùng phương án tương thích được xác minh. |
| Một chuyên gia bị quá tải | Nhiều story cùng chờ duy nhất một người. | Ghép cặp, chia tri thức, giới hạn WIP và sắp ưu tiên. | Chuyển năng lực hỗ trợ hoặc chọn lát khác không phụ thuộc chuyên gia. |
| Kiểm thử tích hợp dồn về cuối | Nhiều thành phần “xong code” nhưng chưa kiểm tra cùng nhau. | Tích hợp thường xuyên, môi trường thử sớm, DoD phù hợp. | Giảm phạm vi phát hành, ưu tiên ổn định và xử lý lỗi cốt lõi. |
| Phê duyệt bảo mật mất nhiều thời gian | Chưa rõ bằng chứng hoặc tiêu chuẩn cần nộp. | Mời chuyên gia sớm, chuẩn bị tài liệu và kiểm tra theo phần. | Hoãn phần không đạt yêu cầu; không bỏ qua kiểm soát bắt buộc. |

### 9.1. Điểm kiểm tra lại (replanning trigger)

Nhóm có thể đặt các **điểm kiểm tra** theo điều kiện, ví dụ:

- Sau một lần thử tích hợp đầu tiên, nếu luồng cơ bản chưa chạy được, xem lại phạm vi Sprint hoặc mục tiêu phát hành.
- Nếu một hạng mục đã bị chặn vượt mức nhóm thống nhất, chủ động điều phối thay vì chờ họp định kỳ.
- Nếu dữ liệu phản hồi bác bỏ giả thuyết giá trị, dừng bổ sung các tính năng dựa trên giả thuyết đó và xem lại Product Backlog.
- Nếu phát hiện rủi ro bảo mật nghiêm trọng, tạm dừng phát hành phần liên quan để xử lý theo chính sách phù hợp.

Không có một số ngày chờ hay ngưỡng WIP chuẩn dùng cho mọi nhóm. Các ngưỡng cần được xây từ bối cảnh, dữ liệu dòng công việc, mức nghiêm trọng và mục tiêu dịch vụ.

### 9.2. Dự phòng không đồng nghĩa với thời gian trống vô nghĩa

Nhóm có thể bảo vệ một phần năng lực cho sự cố, làm rõ phụ thuộc hoặc cải tiến kỹ thuật. Khoảng dự phòng phải được **thảo luận minh bạch** thay vì bị tự động lấp bằng các cam kết tính năng mới. Nếu rủi ro không xảy ra, nhóm có thể hoàn thành công việc ưu tiên tiếp theo; nếu rủi ro xảy ra, nhóm có khả năng phản ứng mà không buộc phải dựa vào tăng ca kéo dài.

## 10. Xử lý phụ thuộc trong Scrum, Kanban và XP

### 10.1. Scrum: bảo vệ Sprint Goal, thương lượng phạm vi

Trong Scrum, **Product Backlog** được làm rõ và sắp xếp theo giá trị; **Sprint Planning** giúp Developers lựa chọn phần có thể làm để hướng tới **Sprint Goal**. Khi cân nhắc công việc, nhóm cần thấy được những phụ thuộc quan trọng có thể ảnh hưởng khả năng tạo Increment đạt **Definition of Done**.

Các thực hành hữu ích:

1. **Product Backlog refinement:** mời nhóm liên quan khi cần xác nhận hợp đồng, quy tắc và đầu vào; chia hạng mục lớn hoặc rủi ro.
2. **Sprint Planning:** đặt mục tiêu có ý nghĩa, kiểm tra năng lực thực tế và phụ thuộc gần, tránh chọn toàn những hạng mục đang chờ một đội khác.
3. **Daily Scrum:** kiểm tra tiến độ tới Sprint Goal, làm rõ blocker và phối hợp gỡ chặn trong ngày.
4. **Sprint Review:** cùng các bên xem kết quả đã tích hợp và điều chỉnh backlog theo phản hồi, không chỉ báo cáo trạng thái.
5. **Sprint Retrospective:** kiểm tra xu hướng chờ đợi, làm lại và phương pháp phối hợp giữa nhóm.

**Khi phụ thuộc thay đổi giữa Sprint**, Developers và Product Owner có thể làm rõ hoặc thương lượng phạm vi để bảo vệ Sprint Goal. Không nên mặc định giữ nguyên mọi story bằng cách tăng ca hoặc hạ tiêu chuẩn chất lượng. Nếu Sprint Goal không còn giá trị, Scrum có cơ chế hủy Sprint trong trường hợp thích hợp; đây là quyết định của Product Owner, không phải biện pháp thường ngày cho mọi blocker.

Một nhóm Scrum không cần mở thêm “Sprint phụ thuộc” riêng hoặc chờ buổi Review mới nói với nhóm khác về API bị lỗi. Trao đổi kịp thời giúp giảm thời gian chờ và duy trì nhịp phản hồi.

### 10.2. Kanban: nhìn thấy blocker và quản lý dòng công việc

Kanban giúp nhóm trực quan hóa các trạng thái, xác định chính sách luồng công việc và **giới hạn WIP** để tránh bắt đầu quá nhiều hạng mục cùng lúc.

~~~text
Sẵn sàng -> Đang xử lý -> Chờ tích hợp -> Đang kiểm tra -> Hoàn thành
              WIP: 3         WIP: 2           WIP: 2
~~~

Giới hạn trong sơ đồ là **ví dụ**, không phải quy định. Nếu cột “Chờ tích hợp” đã đầy, nhóm nên ưu tiên gỡ chặn, mời người cung cấp đầu vào hoặc điều chỉnh cách chia việc trước khi kéo thêm nhiều hạng mục mới vào “Đang xử lý”.

Những thông tin nên được hiển thị:

- Hạng mục nào bị chặn, từ khi nào, bởi đầu ra gì.
- Người điều phối và người cung cấp đầu vào.
- Hành động tiếp theo và tín hiệu cần tăng mức ưu tiên giải quyết.
- Công việc nào còn tiến được độc lập mà không tạo thêm rủi ro tích hợp.

Kanban không bắt buộc Sprint để có kế hoạch thích ứng. Nhóm vẫn có thể định kỳ xem lại ưu tiên, phân tích flow metrics và đổi chính sách luồng công việc.

### 10.3. XP: giữ thay đổi nhỏ và tích hợp an toàn

Các thực hành **Extreme Programming (XP)** như TDD, lập trình cặp, tích hợp liên tục, thiết kế đơn giản và tái cấu trúc có thể giúp giảm chi phí khi một hợp đồng hoặc quy tắc thay đổi.

Ví dụ, khi API thanh toán đổi cách biểu diễn trạng thái “đang xử lý”, bộ kiểm thử tích hợp và các thử nghiệm theo quy tắc nghiệp vụ giúp phát hiện sai lệch sớm. Thiết kế module có trách nhiệm rõ và thử nghiệm nhỏ giúp nhóm sửa một phần thay vì phải thay toàn bộ hệ thống.

XP không xóa phụ thuộc vào đối tác hay nghiệp vụ, nhưng có thể **giảm độ khó của việc điều chỉnh phần mềm** khi các phụ thuộc ấy thay đổi.

## 11. Đo lường tác động của phụ thuộc lên dòng công việc

Không có một chỉ số duy nhất cho biết mức độ phụ thuộc của nhóm có “tốt” hay không. Nên kết hợp **thời gian chờ, dòng công việc, chất lượng và mức đạt giá trị**.

| Chỉ số/tín hiệu | Định nghĩa thực dụng | Cách sử dụng |
|---|---|---|
| **Blocked time** | Tổng thời gian một hạng mục thực sự không thể tiến do phụ thuộc đã ghi nhận. | Tìm nguồn chờ đợi có tác động lớn nhất để giảm hoặc điều phối. |
| **Blocker age** | Thời gian từ lúc blocker hiện tại được ghi nhận đến lúc xem xét. | Phát hiện blocker có nguy cơ bị bỏ quên trước khi gây chậm kéo dài. |
| **WIP** | Số hạng mục đang thực hiện theo chính sách nhóm. | WIP tăng trong lúc nhiều việc chờ có thể báo hiệu mở việc quá nhiều. |
| **Cycle time** | Thời gian từ lúc bắt đầu công việc đến lúc hoàn thành theo định nghĩa nhóm. | Quan sát mức biến động và tác động của việc chờ đầu vào. |
| **Throughput** | Số hạng mục hoàn thành trong một khoảng thời gian. | Xem xu hướng cùng kích thước công việc, không biến thành chỉ tiêu cá nhân. |
| **Work item age** | Thời gian hạng mục đang mở đã nằm trong luồng xử lý. | Xác định việc có nguy cơ trễ ngay cả khi chưa hoàn thành. |
| **Lỗi tích hợp/làm lại** | Số lỗi hoặc lượng làm lại do hiểu sai hợp đồng và tích hợp muộn. | Đánh giá hiệu quả của chia nhỏ, contract tests và trao đổi sớm. |
| **Outcome sản phẩm** | Thay đổi có ý nghĩa đối với người dùng sau bàn giao. | Kiểm tra việc gỡ phụ thuộc có tạo giá trị thật, không chỉ tạo thêm output. |

**Lead time** cũng hữu ích khi định nghĩa điểm bắt đầu và kết thúc rõ, ví dụ từ lúc tiếp nhận yêu cầu đến lúc bàn giao. Khi phân tích phụ thuộc, nên phân biệt thời gian chờ **trước khi bắt đầu**, thời gian bị chặn **sau khi bắt đầu** và thời gian xử lý thực tế.

### 11.1. Ví dụ đọc số liệu

Giả sử nhóm ghi nhận trong ba chu kỳ minh họa:

| Quan sát | Chu kỳ 1 | Chu kỳ 2 | Chu kỳ 3 |
|---|---:|---:|---:|
| WIP trung bình | 6 | 9 | 12 |
| Cycle time trung vị (ngày) | 5 | 8 | 11 |
| Throughput (hạng mục/chu kỳ) | 10 | 10 | 9 |
| Hạng mục từng bị chặn vì tích hợp | 2 | 5 | 7 |

Đây là **dữ liệu giả định để học cách phân tích**, không phải số đo chuẩn của một đội Agile. Mô hình gợi ý số việc đang mở và thời gian hoàn thành tăng trong khi thông lượng không cải thiện. Nhóm nên tìm hiểu chỗ chờ tích hợp, giảm WIP, thương lượng đầu ra nhỏ với nhóm liên quan và kiểm tra hiệu quả sau thử nghiệm.

Khi theo dõi thay đổi, cần giữ định nghĩa chỉ số nhất quán. Một đợt có nhiều hạng mục lớn hơn hoặc cố ý đầu tư vào hạ tầng cũng có thể làm cycle time tăng tạm thời. Không nên rút kết luận từ một con số mà bỏ qua bối cảnh.

## 12. Case study minh họa: thay đổi kế hoạch khi cổng thanh toán bị chậm

**Tình huống dưới đây hoàn toàn giả định.** Một nhóm sáu người đang xây tính năng đặt hàng trực tuyến cho doanh nghiệp bán lẻ. Mục tiêu phát hành ban đầu là “khách đặt và thanh toán thành công bằng một phương thức mới”. Nhóm cần tích hợp với cổng thanh toán của đối tác và lấy trạng thái giữ hàng từ hệ thống kho.

### 12.1. Kế hoạch ban đầu và phụ thuộc chưa được nhìn thấy

Nhóm ban đầu chia việc:

| Nhóm/công việc | Kế hoạch ban đầu | Vấn đề |
|---|---|---|
| Giao diện | Làm toàn bộ trang thanh toán | Chưa biết trạng thái giao dịch và lỗi API để thiết kế thông báo. |
| Backend | Viết toàn bộ tích hợp đối tác | Chưa có sandbox và chưa rõ callback có thể đến lặp không. |
| Kiểm thử | Kiểm tra toàn bộ luồng cuối giai đoạn | Lỗi hợp đồng và dữ liệu sẽ chỉ lộ muộn. |
| Vận hành | Chuẩn bị phát hành sát ngày mục tiêu | Chưa có quy trình đối soát, ghi log phù hợp và kiểm soát bật tính năng. |

Rủi ro lớn nhất không nằm ở số dòng mã của trang thanh toán. **Đường phụ thuộc tích hợp và kiểm chứng giao dịch** chưa được mô hình hóa, còn kế hoạch đang dựa vào giả định đối tác giao sandbox đúng hạn.

### 12.2. Nhóm lập lại bản đồ phụ thuộc và mục tiêu tối thiểu

Sau cuộc trao đổi giữa nghiệp vụ, phát triển, kiểm thử và đại diện tích hợp, nhóm xác định:

1. Có thể giao trước **tổng tiền và tạo đơn ở trạng thái chờ thanh toán**, với quy tắc tồn kho tối thiểu được xác nhận.
2. Có thể dùng **hợp đồng dự thảo và phản hồi mô phỏng** để kiểm tra giao diện xử lý trạng thái, nhưng phải đánh dấu rõ chưa tích hợp thật.
3. Phải kiểm tra thật **callback, xử lý lặp, xác thực nguồn, ghi nhận trạng thái và trường hợp lỗi** trước khi nhận tiền.
4. Phải có **người chịu trách nhiệm xác nhận quy tắc giữ hàng** khi thanh toán chờ.
5. Nếu đối tác chưa sẵn sàng tại điểm kiểm tra, nhóm sẽ **không bật thanh toán thật**; thay vào đó trình diễn phần đặt hàng có thể kiểm chứng và cập nhật dự báo.

Thay vì coi cả tính năng thanh toán là một khối, nhóm lựa chọn các lát và thước đo rõ ràng.

### 12.3. Kế hoạch điều chỉnh

| Lát công việc | Đầu ra có thể kiểm tra | Phụ thuộc quan trọng | Điều kiện tiếp tục |
|---|---|---|---|
| **Lát 1 — Xác nhận đơn** | Khách nhìn tổng tiền và tạo được đơn chờ thanh toán. | Quy tắc giá, tồn kho tối thiểu. | Tiêu chí chấp nhận và kiểm tra dữ liệu đạt yêu cầu. |
| **Lát 2 — Chuẩn bị tích hợp** | Luồng trạng thái thanh toán và kiểm thử hợp đồng với mô phỏng. | API contract, dữ liệu mẫu, quyết định nghiệp vụ. | Các trạng thái chính và lỗi được mô tả, test có thể chạy. |
| **Lát 3 — Kiểm tra thật** | Xác minh giao dịch thật trong môi trường được phép, xử lý callback lặp/lỗi. | Sandbox, bảo mật, đội thanh toán, hệ thống kho. | Có bằng chứng kiểm thử tích hợp và các kiểm soát cần thiết. |
| **Lát 4 — Mở thử giới hạn** | Một nhóm người dùng được dùng phương thức thanh toán mới. | Điều kiện vận hành, giám sát, quy trình khôi phục. | Outcome và guardrail được theo dõi; có cơ chế dừng khi cần. |

Khi sandbox đến muộn, nhóm vẫn có thể **hoàn thành lát 1 và một phần của lát 2**, nhờ đó nhận phản hồi sớm về tổng tiền và thao tác đặt đơn. Lát 3–4 được điều chỉnh dựa trên bằng chứng mới, không lấy kết quả từ mock làm bằng chứng sẵn sàng nhận thanh toán thật.

### 12.4. Cuộc trao đổi khi phát sinh sự cố phụ thuộc

Ví dụ, ngày kiểm tra đến nhưng đối tác chưa cấp sandbox:

| Vai trò | Câu hỏi/quyết định |
|---|---|
| **Product Owner / nghiệp vụ** | “Giá trị nào có thể bàn giao an toàn trước? Có chấp nhận phát hành luồng đơn chờ thanh toán cho nhóm nội bộ không?” |
| **Developers** | “Phần nào đã kiểm chứng độc lập? Phần nào chỉ dùng mock? Phạm vi tích hợp thật còn rủi ro gì?” |
| **Người có góc nhìn kiểm thử** | “Những hành vi nào đã có bằng chứng, những hành vi nào chưa thể xác minh? Guardrail nào bắt buộc trước khi mở?” |
| **Nhóm tích hợp đối tác** | “Thời điểm có môi trường hoặc các trường hợp thử tối thiểu nào có thể xác nhận? Có phương án hỗ trợ kỹ thuật nào khác?” |
| **Vận hành và bảo mật** | “Cần điều kiện gì để nhận giao dịch thật, giám sát và xử lý lỗi an toàn?” |

Kết quả của trao đổi không nên chỉ là “chuyển deadline thêm một tuần” nếu chưa có bằng chứng. Nhóm cần cập nhật **phạm vi, mốc kiểm tra, giả định, độ tin cậy của dự báo và điều kiện phát hành**.

### 12.5. Điều gì được bảo toàn khi đổi hướng?

Nhóm không vứt bỏ toàn bộ công việc đã làm. Họ giữ được:

- Luồng đặt đơn và tính tổng tiền có thể được đánh giá.
- Kiến thức về quy tắc, dữ liệu, hợp đồng và tình huống lỗi.
- Bộ kiểm thử cho những hành vi đã rõ.
- Khả năng mở một phần phạm vi an toàn mà không phụ thuộc hoàn toàn vào đối tác.
- Các phương án lựa chọn khi thông tin mới đến.

Đây chính là **khả năng đổi hướng**: thay đổi thứ tự hoặc phạm vi bàn giao trên cơ sở bằng chứng, trong khi vẫn giữ chất lượng và mục tiêu giá trị đã thống nhất.

## 13. Những cách xử lý phụ thuộc phản tác dụng

| Cách làm | Vì sao nguy hiểm? | Cách cải thiện |
|---|---|---|
| Coi mọi phụ thuộc là lý do để không bắt đầu bất kỳ việc gì. | Trì hoãn cả phần có thể học hoặc bàn giao độc lập. | Tìm lát giá trị, spike hoặc chuẩn bị kiểm thử không phụ thuộc. |
| Giấu phụ thuộc cho đến khi công việc bị chặn. | Không còn thời gian thương lượng hoặc đổi phạm vi. | Ghi đầu ra cần thiết và mốc kiểm tra sớm khi làm rõ backlog. |
| Lập kế hoạch theo ngày cứng mà không ghi giả định. | Tạo sự chắc chắn giả, khiến trì hoãn lan truyền. | Dự báo theo bằng chứng và điều kiện; cập nhật khi rủi ro đổi. |
| Tách nhóm theo tầng kỹ thuật rồi chỉ tích hợp cuối dự án. | Tăng thời gian chờ và phát hiện lỗi muộn. | Chia lát dọc, hợp đồng rõ, tích hợp thường xuyên. |
| Dùng mock rồi coi là đã tích hợp xong. | Sai lệch hợp đồng và lỗi thực tế chưa được kiểm chứng. | Lên kế hoạch kiểm thử thật; tách trạng thái “mô phỏng” và “đạt tích hợp”. |
| Bắt đầu thêm nhiều story khi một story bị chặn. | WIP tăng, chuyển ngữ cảnh và công việc dở dang nhiều hơn. | Ưu tiên gỡ chặn, hỗ trợ tích hợp và giới hạn WIP. |
| Dùng feature flag để bỏ qua kiểm soát bảo mật/chất lượng. | Rủi ro vẫn tồn tại khi bật tính năng. | Chỉ mở cho phạm vi đã đủ điều kiện, có giám sát và rollback phù hợp. |
| Tạo quá nhiều abstraction để “phòng mọi thay đổi”. | Chi phí thiết kế và bảo trì vượt lợi ích thực tế. | Chỉ đầu tư vào điểm linh hoạt có giá trị hoặc rủi ro rõ. |
| Mỗi nhóm tối ưu lịch riêng, không đồng thuận đầu ra. | Cam kết xung đột, không tạo dòng giá trị hoàn chỉnh. | Thống nhất mục tiêu và tiêu chí giao nhận xuyên nhóm. |
| Coi tăng ca là kế hoạch dự phòng mặc định. | Tốc độ ngắn hạn khó duy trì, chất lượng và khả năng phản hồi giảm. | Điều chỉnh phạm vi, năng lực và thứ tự ưu tiên một cách minh bạch. |

## 14. Checklist áp dụng cho một hạng mục có phụ thuộc

Trước khi đưa một hạng mục vào kế hoạch gần, nhóm có thể kiểm tra:

- [ ] Mục tiêu người dùng và giá trị mong muốn đã được làm rõ chưa?
- [ ] Có liệt kê các phụ thuộc **thật sự cần thiết**, không chỉ liệt kê tên nhóm liên quan chưa?
- [ ] Biết **đầu ra cụ thể**, người cung cấp và người điều phối cho từng phụ thuộc trọng yếu chưa?
- [ ] Có phân biệt phụ thuộc đã biết, blocker hiện tại và giả định cần kiểm tra chưa?
- [ ] Có thể chia lát dọc, giảm phạm vi hoặc kiểm chứng một phần sớm hơn không?
- [ ] Với tích hợp, hợp đồng API, trạng thái lỗi, dữ liệu mẫu và kế hoạch kiểm thử thật đã đủ rõ chưa?
- [ ] Có quyết định kiến trúc hoặc nghiệp vụ nào nên giữ mở đến khi có thêm bằng chứng không?
- [ ] Những kiểm soát bảo mật, quyền riêng tư, chất lượng và vận hành bắt buộc đã được nhận diện chưa?
- [ ] Có **tín hiệu cần đổi kế hoạch** và phương án dự phòng không?
- [ ] Các bên liên quan biết điều gì đã được xác minh và điều gì mới chỉ là mô phỏng chưa?
- [ ] Phần việc có thể hoàn thành theo **Definition of Done** và nhận phản hồi trong nhịp phù hợp chưa?
- [ ] Có cách theo dõi blocker, thời gian chờ và ảnh hưởng tới outcome sau bàn giao chưa?

Checklist là công cụ hỗ trợ thảo luận, **không phải cổng phê duyệt cố định**. Với hạng mục khám phá, chính mục tiêu có thể là làm rõ một phụ thuộc chưa biết; khi đó cần thống nhất kết quả học hỏi và giới hạn thực hiện thay vì đòi mọi câu trả lời có sẵn.

## 15. Tóm tắt

**Xử lý phụ thuộc trong kế hoạch Agile** không có nghĩa xóa tất cả quan hệ giữa công việc, nhóm và hệ thống. Điều quan trọng là **biến những phụ thuộc còn ẩn thành thông tin có thể hành động**, làm rõ đầu ra, người điều phối, mức rủi ro, thời điểm kiểm tra và lựa chọn thay thế.

Khả năng đổi hướng được bảo toàn khi nhóm lập kế hoạch chi tiết cho việc gần nhưng giữ linh hoạt cho việc xa, chia nhỏ theo lát giá trị, dùng phản hồi và tích hợp sớm, ghi nhận giả định, hạn chế WIP và liên tục điều chỉnh dự báo. Scrum hỗ trợ mục tiêu và các vòng kiểm tra–thích ứng; Kanban hỗ trợ quản lý dòng công việc và blocker; XP giúp thay đổi phần mềm an toàn khi đầu vào hoặc hợp đồng thay đổi.

Một kế hoạch tốt không phải kế hoạch **không bao giờ đổi**. Đó là kế hoạch giúp nhóm **biết cần đạt giá trị gì, điều gì đang giới hạn lựa chọn và sẽ hành động ra sao khi có thông tin mới**, để tiếp tục giao phần mềm hữu ích mà không đánh đổi chất lượng thiết yếu.
