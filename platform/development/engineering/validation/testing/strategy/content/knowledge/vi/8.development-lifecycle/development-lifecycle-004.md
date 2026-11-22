# Vị trí của TDD, BDD và ATDD trong chiến lược phản hồi

Kiểm thử chỉ tạo ra giá trị khi kết quả đến đủ sớm để nhóm còn có thể hành động. Nếu nhóm chỉ xác minh sản phẩm sau khi hoàn tất một đợt phát triển dài, lỗi yêu cầu, lỗi thiết kế và lỗi mã nguồn có thể đã lan sang nhiều thành phần. Chiến lược phản hồi tốt đưa hoạt động kiểm thử vào nhiều thời điểm của vòng đời phát triển, từ lúc làm rõ nhu cầu đến khi triển khai và vận hành.

Test-Driven Development (TDD), Behavior-Driven Development (BDD) và Acceptance Test-Driven Development (ATDD) là ba cách tiếp cận giúp nhóm nhận phản hồi sớm theo những góc nhìn khác nhau. TDD hỗ trợ thiết kế và kiểm tra mã nguồn ở mức gần với người phát triển. BDD giúp các bên thống nhất hành vi bằng ví dụ cụ thể và ngôn ngữ chung. ATDD giúp nhóm xác định điều kiện chấp nhận trước khi xây dựng chức năng. Khi kết hợp hợp lý, chúng tạo thành các vòng phản hồi liên kết từ mục tiêu người dùng đến quy tắc nghiệp vụ và chi tiết triển khai.

## 1. Chiến lược phản hồi trong vòng đời phát triển

Một chiến lược phản hồi xác định **ai cần biết điều gì, vào thời điểm nào, từ loại kiểm thử nào và sẽ làm gì với kết quả đó**. Mục tiêu là giảm thời gian giữa lúc tạo ra sai lệch và lúc nhóm phát hiện, hiểu và sửa được sai lệch.

Có thể xem phản hồi theo ba phạm vi:

- **Phản hồi ở mức mã nguồn:** logic, lớp, hàm, thành phần và hợp đồng kỹ thuật có hoạt động như thiết kế không?
- **Phản hồi ở mức hành vi:** hệ thống có thực hiện đúng quy tắc và ví dụ nghiệp vụ mà các bên đã thống nhất không?
- **Phản hồi ở mức chấp nhận:** chức năng hoàn chỉnh có đáp ứng nhu cầu, tiêu chí chấp nhận và điều kiện phát hành không?

Ba phạm vi này liên kết với nhau. Một chức năng có thể vượt qua kiểm thử đơn vị nhưng vẫn sai quy tắc nghiệp vụ; một kịch bản nghiệp vụ có thể đúng trong môi trường kiểm thử nhưng chưa đáp ứng yêu cầu vận hành hoặc trải nghiệm người dùng.

Phản hồi càng gần thời điểm tạo thay đổi thì thường càng dễ xác định nguyên nhân và chi phí sửa chữa càng thấp. Tuy nhiên, không phải mọi kiểm thử đều có thể chạy ở cùng một tốc độ hoặc cùng một môi trường. Nhóm cần chọn nhiều vòng kiểm tra phù hợp với rủi ro, từ kiểm thử tự động nhanh đến xác minh tích hợp và chấp nhận ở phạm vi rộng hơn.

## 2. TDD, BDD và ATDD là gì?

| Cách tiếp cận | Điểm bắt đầu | Trọng tâm | Câu hỏi chính |
|---|---|---|---|
| TDD — Test-Driven Development | Một hành vi nhỏ cần triển khai | Thiết kế mã và xác minh logic ở mức kỹ thuật | Mã vừa viết có thực hiện đúng hành vi nhỏ này không? |
| BDD — Behavior-Driven Development | Hành vi người dùng hoặc quy tắc nghiệp vụ | Làm rõ hành vi bằng ví dụ và ngôn ngữ chung | Hệ thống nên hành xử thế nào trong tình huống này? |
| ATDD — Acceptance Test-Driven Development | Nhu cầu và tiêu chí chấp nhận | Xác định điều kiện chấp nhận trước khi triển khai | Làm thế nào biết chức năng hoàn thành đáp ứng yêu cầu? |

Các cách tiếp cận có thể dùng cùng một ví dụ hoặc một số kỹ thuật giống nhau, nhưng khác nhau ở mục đích, phạm vi và người tham gia. TDD thường do người phát triển sử dụng trong vòng lặp mã nguồn. BDD là cách cộng tác để khám phá và mô tả hành vi. ATDD tổ chức việc xác định tiêu chí chấp nhận và kiểm thử chấp nhận trước khi xây dựng giải pháp.

### 2.1. TDD — Phát triển hướng kiểm thử

TDD là phương pháp phát triển trong đó người phát triển viết một kiểm thử tự động cho hành vi nhỏ trước khi viết mã triển khai. Kiểm thử ban đầu thường thất bại vì hành vi chưa tồn tại. Sau đó, người phát triển viết lượng mã tối thiểu để kiểm thử đạt và tái cấu trúc mã khi cần.

Vòng lặp TDD thường được mô tả bằng ba bước:

1. **Red:** viết một kiểm thử mô tả hành vi nhỏ và xác nhận nó thất bại vì lý do mong đợi.
2. **Green:** viết mã tối thiểu để kiểm thử đạt.
3. **Refactor:** cải thiện cấu trúc mã và giữ toàn bộ kiểm thử liên quan vẫn đạt.

~~~mermaid
flowchart LR
    A["Red<br/>Viết kiểm thử và thấy thất bại"] --> B["Green<br/>Viết mã tối thiểu để đạt"]
    B --> C["Refactor<br/>Cải thiện thiết kế"]
    C --> A
~~~

Ví dụ, hàm tính số tiền giảm giá cần áp dụng cho một đơn hàng. Người phát triển bắt đầu bằng kiểm thử cho trường hợp đơn đủ điều kiện, sau đó bổ sung các trường hợp đơn dưới mức tối thiểu, mã hết hạn và khách hàng không thuộc nhóm áp dụng. Mỗi vòng nhỏ giúp làm rõ hợp đồng của hàm và giới hạn của logic.

TDD thường dùng ở cấp đơn vị hoặc thành phần, nơi kiểm thử chạy nhanh và có thể chỉ ra chính xác hành vi sai. Một số nhóm cũng áp dụng test-first cho API hoặc thành phần tích hợp. TDD không có nghĩa mọi kiểm thử phải kiểm tra chi tiết nội bộ của mã; kiểm thử tốt nên tập trung vào hành vi có ý nghĩa và giữ được khả năng thay đổi thiết kế.

**Lợi ích thường thấy:**

- Phát hiện lỗi logic ngay trong lúc viết mã.
- Làm rõ đầu vào, đầu ra, điều kiện biên và hành vi lỗi.
- Khuyến khích thiết kế thành phần có trách nhiệm rõ và dễ kiểm tra.
- Tạo bộ hồi quy nhanh để hỗ trợ tái cấu trúc.
- Giảm thời gian điều tra khi một thay đổi làm sai hành vi đã có.

**Giới hạn cần hiểu:**

- TDD không tự bảo đảm yêu cầu nghiệp vụ đã đúng.
- Kiểm thử có thể yếu nếu chỉ kiểm tra chính cách triển khai mà người viết đang nghĩ đến.
- Kiểm thử đơn vị không thay thế kiểm thử tích hợp, bảo mật, hiệu năng hoặc chấp nhận.
- Việc viết test trước không hữu ích nếu expected result chưa có căn cứ hoặc kiểm thử không kiểm tra đúng hành vi.

### 2.2. BDD — Phát triển hướng hành vi

BDD mở rộng cách suy nghĩ test-first sang việc khám phá và mô tả hành vi mà người dùng hoặc nghiệp vụ mong đợi. Thay vì bắt đầu từ một hàm hoặc lớp, nhóm bắt đầu bằng ví dụ cụ thể về cách hệ thống phải phản hồi trong một tình huống.

BDD khuyến khích sự cộng tác giữa các vai trò như chủ sản phẩm, chuyên gia nghiệp vụ, BA, người phát triển và tester. Nhóm cùng làm rõ:

- Ai đang gặp nhu cầu hoặc vấn đề nào?
- Bối cảnh trước khi hành vi xảy ra là gì?
- Hành động nào được thực hiện?
- Kết quả có thể quan sát được là gì?
- Có ngoại lệ hoặc quy tắc nào cần làm rõ?

Một cách viết phổ biến là cấu trúc **Given–When–Then**:

- **Given:** bối cảnh hoặc điều kiện ban đầu.
- **When:** hành động hoặc sự kiện xảy ra.
- **Then:** kết quả quan sát được mong đợi.

Ví dụ:

~~~gherkin
Feature: Áp dụng mã giảm giá

  Scenario: Khách hàng áp dụng mã hợp lệ cho đơn đủ điều kiện
    Given mã giảm giá "SAVE10" còn hiệu lực
    And đơn hàng có giá trị đủ mức tối thiểu
    And khách hàng thuộc nhóm được áp dụng
    When khách hàng áp dụng mã "SAVE10"
    Then hệ thống tính giảm giá theo chính sách đã duyệt
    And tổng tiền đơn hàng được cập nhật chính xác
~~~

Ví dụ này là cách diễn đạt hành vi, chưa phải đặc tả đầy đủ của mọi trường hợp. Nhóm cần bổ sung ví dụ cho mã hết hạn, đơn dưới ngưỡng, khách không đủ điều kiện, mã đã sử dụng và việc kết hợp nhiều mã nếu nghiệp vụ có quy tắc đó.

BDD không đồng nghĩa với việc phải dùng một công cụ cú pháp Gherkin hoặc tự động hóa mọi kịch bản. Giá trị cốt lõi là cuộc trao đổi dựa trên ví dụ, thuật ngữ thống nhất và kết quả có thể quan sát. Công cụ có thể giúp biến ví dụ thành kiểm thử tự động, nhưng một kịch bản Given–When–Then không rõ hoặc không có oracle vẫn không phải bằng chứng đáng tin cậy.

**Lợi ích thường thấy:**

- Làm rõ yêu cầu và giảm cách hiểu khác nhau giữa nghiệp vụ và kỹ thuật.
- Phát hiện sớm trường hợp biên và ngoại lệ.
- Tạo ngôn ngữ chung để thảo luận, review và truy vết.
- Cung cấp ví dụ có thể dùng trong tài liệu, kiểm thử thủ công hoặc tự động.

**Giới hạn cần hiểu:**

- Viết nhiều kịch bản bằng cú pháp BDD không thay thế việc trao đổi thực chất.
- Kịch bản quá chi tiết về thao tác giao diện dễ trở nên mong manh và khó bảo trì.
- Nếu các ví dụ không bao phủ rủi ro quan trọng, bộ BDD vẫn có thể bỏ sót lỗi.
- Cần quản lý từ vựng nghiệp vụ và nguồn xác nhận để tránh nhiều cách diễn giải.

### 2.3. ATDD — Phát triển hướng kiểm thử chấp nhận

ATDD là cách tiếp cận trong đó nhóm xác định và thống nhất kiểm thử chấp nhận trước khi triển khai chức năng. Kiểm thử chấp nhận thể hiện điều kiện mà sản phẩm hoặc thay đổi phải đáp ứng để được xem là hoàn thành theo nhu cầu đã thống nhất.

ATDD thường có sự tham gia của ba nhóm góc nhìn:

- **Nghiệp vụ:** nhu cầu, quy tắc, giá trị mong đợi và điều kiện chấp nhận.
- **Phát triển:** tính khả thi, thiết kế, phụ thuộc và cách triển khai.
- **Kiểm thử:** khả năng kiểm chứng, dữ liệu, tình huống biên và rủi ro.

Nhóm có thể dùng các buổi thảo luận ví dụ, bảng quyết định, tiêu chí chấp nhận hoặc kịch bản Given–When–Then để tạo bộ kiểm thử chấp nhận. Những kiểm thử này có thể được tự động hóa ở cấp API, dịch vụ, tích hợp hoặc giao diện, tùy nơi có thể xác minh hành vi ổn định và có ý nghĩa.

Ví dụ với mã giảm giá, trước khi triển khai, nhóm thống nhất:

- Mã phải còn hiệu lực tại thời điểm áp dụng.
- Đơn phải đạt mức tối thiểu theo chính sách.
- Khách hàng phải thuộc nhóm được phép sử dụng.
- Số tiền giảm và tổng tiền phải được tính theo quy tắc đã phê duyệt.
- Khi điều kiện không đạt, hệ thống phải từ chối và cung cấp lý do phù hợp.

Từ các điều kiện này, nhóm tạo kiểm thử chấp nhận cho cả trường hợp thành công và thất bại. Khi chức năng được triển khai, kết quả của bộ kiểm thử giúp nhóm đánh giá liệu yêu cầu đã được đáp ứng hay chưa.

**Lợi ích thường thấy:**

- Đưa tiêu chí hoàn thành về gần thời điểm làm rõ yêu cầu.
- Giảm tranh luận ở cuối dự án về việc chức năng có đúng mong đợi hay không.
- Tạo cơ sở chung cho phát triển, kiểm thử và chủ sản phẩm.
- Hỗ trợ quyết định phát hành bằng bằng chứng đã thống nhất.

**Giới hạn cần hiểu:**

- Bộ kiểm thử chấp nhận có thể tốn công xây dựng và bảo trì nếu chọn sai cấp hoặc quá phụ thuộc giao diện.
- Kiểm thử chấp nhận không bao phủ toàn bộ chất lượng phi chức năng.
- Tiêu chí chấp nhận thiếu cụ thể sẽ tạo ra expected result mơ hồ.
- ATDD cần người có thẩm quyền tham gia và quyết định khi có xung đột yêu cầu.

## 3. Khác nhau và quan hệ bổ trợ

TDD, BDD và ATDD không phải ba tên gọi cho cùng một loại test. Chúng có thể cùng kiểm tra một chức năng nhưng tạo ra phản hồi ở những thời điểm và góc nhìn khác nhau.

| Tiêu chí | TDD | BDD | ATDD |
|---|---|---|---|
| Mục tiêu chính | Thiết kế và xác minh logic kỹ thuật qua kiểm thử trước | Khám phá, diễn đạt và xác minh hành vi | Thống nhất điều kiện chấp nhận trước khi triển khai |
| Phạm vi thường gặp | Hàm, lớp, thành phần hoặc hợp đồng kỹ thuật | Hành vi, quy tắc và ví dụ nghiệp vụ | Chức năng hoặc thay đổi theo nhu cầu người dùng |
| Người tham gia chính | Người phát triển | Nghiệp vụ, phát triển, tester và các bên liên quan | Nghiệp vụ, phát triển và tester |
| Đầu ra | Kiểm thử tự động ở mức kỹ thuật và mã nguồn được cải thiện | Ví dụ hành vi, từ vựng chung, kịch bản | Tiêu chí và kiểm thử chấp nhận |
| Thời điểm phản hồi | Trong vòng lặp viết mã | Khi khám phá yêu cầu và trong quá trình phát triển | Trước triển khai và khi xác minh mức chấp nhận |
| Câu hỏi trọng tâm | Thành phần này có hoạt động đúng không? | Hành vi trong tình huống này nên như thế nào? | Chức năng đã đáp ứng điều kiện chấp nhận chưa? |

Một cách hình dung hữu ích là:

- ATDD giúp nhóm xác định điều kiện chấp nhận cho nhu cầu cần giải quyết.
- BDD giúp nhóm diễn đạt và khám phá hành vi bằng ví dụ cụ thể, thường dùng Given–When–Then.
- TDD giúp người phát triển chuyển các quy tắc và ví dụ đã hiểu thành những thay đổi mã nhỏ, có kiểm thử phản hồi nhanh.

BDD và ATDD có phần giao nhau đáng kể. Một nhóm có thể dùng ví dụ BDD làm kiểm thử chấp nhận trong quy trình ATDD. Khác biệt nằm ở mục tiêu tổ chức công việc: BDD nhấn mạnh cách khám phá và mô tả hành vi; ATDD nhấn mạnh việc thống nhất tiêu chí chấp nhận trước khi xây dựng.

TDD và ATDD cũng đều có thể bắt đầu bằng kiểm thử trước mã triển khai, nhưng kiểm thử TDD thường ở mức kỹ thuật nhỏ, còn kiểm thử ATDD thể hiện điều kiện chấp nhận ở góc nhìn nghiệp vụ hoặc người dùng. Một kiểm thử chấp nhận có thể thất bại trước khi tính năng tồn tại, trong khi các kiểm thử TDD sau đó giúp phát triển logic bên trong.

## 4. Đặt TDD, BDD và ATDD vào các giai đoạn phát triển

Không cần chờ đến khi mã nguồn hoàn tất mới bắt đầu kiểm thử. Có thể đưa ba cách tiếp cận vào các giai đoạn như sau:

| Giai đoạn | Hoạt động phù hợp | Kết quả phản hồi |
|---|---|---|
| Khám phá nhu cầu và làm rõ vấn đề | BDD: trao đổi ví dụ, thuật ngữ, quy tắc và ngoại lệ | Nhóm hiểu vấn đề và các cách xử lý có thể có |
| Phân tích và xác định phạm vi | ATDD: thống nhất tiêu chí chấp nhận và ví dụ kiểm thử | Có điều kiện rõ để xác định hoàn thành |
| Thiết kế giải pháp | BDD/ATDD: rà soát kịch bản, luồng, dữ liệu và trường hợp biên | Phát hiện thiếu sót trước khi triển khai |
| Phát triển | TDD: Red–Green–Refactor cho logic và thành phần | Phản hồi nhanh về tính đúng đắn của mã |
| Tích hợp và CI | Chạy kiểm thử đơn vị, hợp đồng, tích hợp và kịch bản chấp nhận tự động phù hợp | Phát hiện sai lệch giữa thành phần và hành vi |
| Kiểm thử hệ thống và chấp nhận | Chạy kịch bản BDD/ATDD, kiểm thử thăm dò và kiểm thử phi chức năng | Xác minh hành vi hoàn chỉnh và rủi ro còn lại |
| Phát hành và vận hành | Theo dõi chỉ số, sự cố, phản hồi người dùng và hồi quy | Phát hiện khoảng cách giữa môi trường kiểm thử và thực tế |

~~~mermaid
flowchart TD
    A["Khám phá nhu cầu<br/>BDD: ví dụ và ngôn ngữ chung"]
    B["Thống nhất chấp nhận<br/>ATDD: tiêu chí và kiểm thử"]
    C["Phát triển từng phần<br/>TDD: Red - Green - Refactor"]
    D["Tích hợp và CI<br/>Kiểm thử hợp đồng, tích hợp, chấp nhận"]
    E["Xác minh hệ thống<br/>BDD/ATDD, thăm dò, phi chức năng"]
    F["Phát hành và vận hành<br/>Theo dõi và phản hồi thực tế"]
    A --> B --> C --> D --> E --> F
    F -. "Bài học và nhu cầu mới" .-> A
    D -. "Phản hồi về yêu cầu" .-> B
    E -. "Phản hồi về hành vi" .-> A
~~~

Sơ đồ mô tả một dòng chảy điển hình, không phải quy trình cứng. Trong phát triển lặp, các bước diễn ra nhiều lần trong mỗi sprint hoặc mỗi thay đổi. BDD có thể tiếp tục trong lúc phát triển; ATDD có thể bổ sung tiêu chí khi khám phá được quy tắc mới; TDD diễn ra liên tục khi mã thay đổi.

## 5. Ví dụ xuyên suốt: chức năng áp dụng mã giảm giá

Giả sử một cửa hàng trực tuyến muốn cho phép khách hàng áp dụng mã giảm giá trong giỏ hàng. Chính sách yêu cầu mã còn hiệu lực, đơn đạt giá trị tối thiểu và khách hàng thuộc nhóm được phép.

### 5.1. BDD: khám phá hành vi bằng ví dụ

Nhóm nghiệp vụ, phát triển và tester cùng thảo luận:

- Mã hết hạn được xử lý thế nào?
- Giá trị tối thiểu được tính trước hay sau khi trừ phí vận chuyển?
- Khách hàng mới và khách hàng hiện tại có chính sách khác nhau không?
- Một mã có thể được sử dụng nhiều lần hay chỉ một lần?
- Nếu hai mã cùng hợp lệ, mã nào được áp dụng?

Nhóm tạo các ví dụ cụ thể để làm rõ từng quy tắc:

~~~gherkin
Feature: Áp dụng mã giảm giá

  Scenario: Mã hợp lệ và đơn đủ điều kiện
    Given mã giảm giá còn hiệu lực
    And giá trị hàng hóa đạt mức tối thiểu
    And khách hàng thuộc nhóm được áp dụng
    When khách hàng áp dụng mã
    Then hệ thống tính giảm giá theo chính sách

  Scenario: Đơn hàng chưa đạt mức tối thiểu
    Given mã giảm giá còn hiệu lực
    And giá trị hàng hóa thấp hơn mức tối thiểu
    When khách hàng áp dụng mã
    Then hệ thống từ chối áp dụng mã
    And tổng tiền không bị thay đổi bởi mã đó
~~~

Những ví dụ này giúp các bên phát hiện câu hỏi chưa được giải đáp và thống nhất ngôn ngữ trước khi viết mã.

### 5.2. ATDD: thống nhất điều kiện chấp nhận

Trước khi phát triển, nhóm chuyển các quyết định thành điều kiện chấp nhận:

| Điều kiện | Kết quả chấp nhận |
|---|---|
| Mã còn hiệu lực, đơn đủ ngưỡng, khách đủ điều kiện | Áp dụng mã và tính giảm giá đúng công thức đã duyệt |
| Mã hết hạn | Từ chối và thông báo lý do |
| Đơn dưới ngưỡng | Từ chối; tổng tiền không bị thay đổi bởi mã |
| Khách không thuộc nhóm áp dụng | Từ chối |
| Yêu cầu áp dụng cùng mã được gửi lặp | Không ghi nhận việc sử dụng hoặc giảm giá trùng |

Nhóm xác nhận nguồn quy tắc, cách tính ngưỡng, thời điểm kiểm tra hiệu lực và cách xử lý khi khách gửi yêu cầu lặp. Từ bảng này có thể tạo kiểm thử chấp nhận ở API hoặc giao diện. Với các kiểm thử tự động, nên chọn điểm xác minh ổn định để tránh phụ thuộc không cần thiết vào chi tiết trình bày.

### 5.3. TDD: triển khai logic với phản hồi nhanh

Người phát triển tách logic thành các thành phần có thể kiểm tra:

- Kiểm tra hiệu lực của mã.
- Xác định khách hàng có thuộc nhóm áp dụng.
- Tính giá trị đủ điều kiện.
- Tính số tiền giảm và tổng tiền mới.
- Ngăn ghi nhận sử dụng mã trùng.

Với từng thành phần, người phát triển viết kiểm thử trước, quan sát thất bại, viết mã tối thiểu để đạt rồi tái cấu trúc. Các trường hợp như đúng ngưỡng, thấp hơn ngưỡng một đơn vị tiền, mã hết hạn tại thời điểm biên và yêu cầu lặp được kiểm tra ở mức phù hợp.

Khi logic thay đổi, kiểm thử TDD chạy nhanh giúp phát hiện sai lệch ngay trong vòng lặp lập trình. Sau đó, kiểm thử tích hợp và chấp nhận xác nhận các thành phần phối hợp đúng theo ví dụ đã thống nhất.

### 5.4. Kết hợp bằng chứng

| Nguồn phản hồi | Bằng chứng | Điều có thể kết luận |
|---|---|---|
| BDD | Ví dụ và quyết định đã thống nhất | Nhóm có cùng cách hiểu về hành vi cần có |
| ATDD | Kiểm thử chấp nhận và kết quả chạy | Chức năng đáp ứng các điều kiện chấp nhận được mô tả |
| TDD | Kiểm thử đơn vị/thành phần | Logic nhỏ hoạt động theo hợp đồng đã xác định |
| Kiểm thử tích hợp | Kết quả giữa dịch vụ giỏ hàng, khuyến mãi và giá | Các thành phần trao đổi và duy trì dữ liệu đúng |
| Theo dõi sau phát hành | Tỷ lệ áp dụng mã, lỗi tính tiền và phản hồi hỗ trợ | Hành vi thực tế có phù hợp với kỳ vọng và rủi ro đã đánh giá không |

Không một nguồn phản hồi nào tự chứng minh toàn bộ chất lượng. Nhóm cần xem chúng như những lớp bằng chứng bổ sung cho nhau.

## 6. Tổ chức vòng phản hồi nhanh và chậm

Một chiến lược hiệu quả phân bổ kiểm thử theo thời gian phản hồi và khả năng phát hiện lỗi:

**Vòng phản hồi nhanh**

- Kiểm thử TDD ở cấp đơn vị hoặc thành phần.
- Kiểm tra kiểu dữ liệu, phân tích tĩnh và review mã.
- Kiểm thử hợp đồng hoặc kiểm thử API nhỏ có thể chạy trong CI.
- Phản hồi ngay khi người phát triển thay đổi mã.

**Vòng phản hồi trung bình**

- Kiểm thử tích hợp giữa các dịch vụ.
- Kịch bản BDD/ATDD ở cấp API hoặc hệ thống nhỏ.
- Kiểm thử cơ sở dữ liệu, sự kiện và phụ thuộc quan trọng.
- Chạy trong pipeline sau khi các kiểm thử nhanh đạt.

**Vòng phản hồi rộng hơn**

- Kiểm thử đầu cuối và chấp nhận theo hành trình người dùng.
- Kiểm thử thăm dò, khả năng sử dụng, tương thích và khả năng tiếp cận.
- Kiểm thử hiệu năng, bảo mật, phục hồi và vận hành.
- Theo dõi sau triển khai và xác minh các chỉ số thực tế.

~~~mermaid
flowchart TB
    A["Vòng nhanh<br/>TDD, unit/component, static checks"]
    B["Vòng trung bình<br/>API, contract, integration, BDD/ATDD"]
    C["Vòng rộng<br/>E2E, acceptance, exploratory, non-functional"]
    D["Môi trường thật<br/>Observability, feedback, incidents"]
    A --> B --> C --> D
    D -. "Phản hồi về rủi ro và hành vi" .-> A
    D -. "Cập nhật ví dụ và tiêu chí" .-> B
~~~

Các vòng này không nhất thiết là những pipeline tách biệt. Có thể chạy một phần kiểm thử trên mỗi pull request, phần khác theo lịch hoặc trước phát hành. Điều quan trọng là kết quả phải đến đúng người, có thời gian phản hồi phù hợp và không tạo quá nhiều tín hiệu nhiễu.

## 7. Cách triển khai trong một nhóm phát triển

### Bước 1: Chọn một luồng nghiệp vụ có giá trị

Bắt đầu với chức năng có rủi ro hoặc thay đổi thường xuyên, chẳng hạn đăng nhập, thanh toán, tính giá hoặc hoàn tiền. Tránh áp dụng toàn bộ phương pháp cùng lúc cho mọi thành phần.

### Bước 2: Làm rõ nhu cầu bằng ví dụ

Tổ chức buổi trao đổi giữa nghiệp vụ, phát triển và kiểm thử. Dùng ví dụ thành công, thất bại, biên và ngoại lệ. Thống nhất thuật ngữ và nguồn xác nhận kết quả mong đợi.

### Bước 3: Viết tiêu chí chấp nhận trước triển khai

Chuyển ví dụ thành điều kiện có thể kiểm chứng. Xác định dữ liệu, trạng thái, kết quả quan sát được và mức độ quan trọng. Làm rõ ai phê duyệt khi các bên có cách hiểu khác nhau.

### Bước 4: Chọn kiểm thử chấp nhận ở cấp phù hợp

Ưu tiên API hoặc cấp dịch vụ khi có thể kiểm tra hành vi nghiệp vụ ổn định ở đó. Dùng kiểm thử giao diện cho hành vi chỉ có thể xác minh qua giao diện, khả năng sử dụng hoặc hành trình người dùng. Không cần tự động hóa mọi ví dụ nếu chi phí bảo trì lớn hơn giá trị.

### Bước 5: Dùng TDD để triển khai từng phần

Người phát triển viết kiểm thử cho logic nhỏ trước khi viết mã. Chạy kiểm thử thường xuyên, giữ phản hồi nhanh và tái cấu trúc khi bộ kiểm thử bảo vệ được hành vi cần thiết.

### Bước 6: Kết nối vào CI

Đưa kiểm thử nhanh vào pipeline thường xuyên. Chạy kiểm thử hợp đồng, tích hợp và chấp nhận ở thời điểm phù hợp. Khi kiểm thử thất bại, báo cáo cần chỉ rõ ví dụ, điều kiện, dữ liệu và bước tái hiện.

### Bước 7: Rà soát và học từ kết quả

Theo dõi lỗi lọt, kiểm thử không ổn định, thời gian phản hồi và những điểm thường xuyên phải làm rõ lại. Cập nhật ví dụ, tiêu chí chấp nhận và bộ kiểm thử khi quy tắc thay đổi.

## 8. Vai trò và trách nhiệm

| Vai trò | Đóng góp trong BDD/ATDD/TDD |
|---|---|
| Product Owner hoặc chủ nghiệp vụ | Giải thích nhu cầu, ưu tiên và phê duyệt hành vi/tiêu chí chấp nhận |
| BA hoặc chuyên gia miền nghiệp vụ | Làm rõ thuật ngữ, quy tắc, ngoại lệ và ví dụ |
| Tester/QA | Đặt câu hỏi, phát hiện khoảng trống, đề xuất dữ liệu và tình huống kiểm thử |
| Developer | Đánh giá tính khả thi, thiết kế giải pháp, viết kiểm thử TDD và triển khai |
| Kiến trúc sư hoặc chủ sở hữu dịch vụ | Làm rõ hợp đồng, phụ thuộc, ranh giới và yêu cầu kỹ thuật |
| DevOps/SRE | Hỗ trợ pipeline, môi trường, quan sát và phản hồi vận hành |

Chất lượng không thuộc riêng một vai trò. Người kiểm thử không nên là người duy nhất viết mọi kịch bản; người phát triển không nên tự quyết định các quy tắc nghiệp vụ; chủ sản phẩm cần tham gia xác nhận những điều kiện ảnh hưởng đến hành vi được chấp nhận.

## 9. Chọn nơi tự động hóa

Tự động hóa nên dựa trên độ ổn định của hành vi, tần suất chạy, mức rủi ro và chi phí bảo trì.

- Tự động hóa kiểm thử TDD thường phù hợp vì chúng nhỏ, chạy nhanh và được thực thi thường xuyên.
- Kịch bản BDD có thể được tự động hóa khi ví dụ ổn định, có kết quả quan sát rõ và có người chịu trách nhiệm bảo trì.
- Kiểm thử ATDD nên được tự động hóa ở cấp mang lại phản hồi tin cậy nhất, thường là API hoặc dịch vụ; chỉ dùng E2E khi cần xác minh phối hợp toàn luồng.
- Những đánh giá cần quan sát con người như khả năng sử dụng, tính dễ hiểu hoặc một số khía cạnh UX vẫn cần kiểm thử thủ công.

Tránh tạo nhiều lớp trừu tượng khiến kịch bản khó đọc hoặc khó chẩn đoán. Một ví dụ nghiệp vụ nên thể hiện điều kiện và kết quả quan trọng; phần thiết lập kỹ thuật có thể được tái sử dụng phía sau.

## 10. Đo lường hiệu quả phản hồi

Có thể theo dõi một nhóm chỉ số kết hợp:

- **Thời gian phản hồi kiểm thử:** từ lúc thay đổi mã đến khi có kết quả đủ tin cậy.
- **Thời gian phát hiện và sửa lỗi:** lỗi được phát hiện ở giai đoạn nào và mất bao lâu để xử lý.
- **Lỗi lọt ra môi trường thật:** số lượng, mức độ nghiêm trọng và nguyên nhân.
- **Độ ổn định của kiểm thử tự động:** tỷ lệ flaky test, số lần chạy lại và thời gian bảo trì.
- **Mức bao phủ tiêu chí chấp nhận:** yêu cầu hoặc ví dụ quan trọng nào đã có kiểm thử và bằng chứng.
- **Tần suất làm rõ lại yêu cầu:** các quy tắc thường xuyên thay đổi hoặc bị hiểu khác nhau.
- **Thời gian pipeline:** tác động của các bộ kiểm thử đến tốc độ tích hợp và phát hành.

Không nên đánh giá thành công chỉ bằng số lượng test case hoặc tỷ lệ kiểm thử tự động. Bộ kiểm thử lớn nhưng phản hồi chậm, khó chẩn đoán hoặc không gắn với rủi ro có thể làm giảm hiệu quả phát triển.

## 11. Những sai lầm thường gặp

- **Đồng nhất TDD với viết unit test sau khi viết mã:** điều cốt lõi của TDD là dùng kiểm thử trước để định hướng hành vi và thiết kế.
- **Cho rằng TDD thay thế kiểm thử hệ thống:** kiểm thử đơn vị không thể chứng minh các dịch vụ phối hợp đúng hoặc đáp ứng nhu cầu người dùng.
- **Đồng nhất BDD với cú pháp Gherkin:** công cụ và cú pháp chỉ hỗ trợ; giá trị chính là trao đổi dựa trên ví dụ và ngôn ngữ chung.
- **Viết kịch bản BDD theo từng thao tác giao diện:** kịch bản quá phụ thuộc UI dễ vỡ khi giao diện thay đổi và làm mờ ý nghĩa nghiệp vụ.
- **Xem ATDD là kiểm thử cuối dự án:** tiêu chí chấp nhận cần được thống nhất trước khi triển khai để định hướng công việc.
- **Tự động hóa mọi kịch bản chấp nhận:** kiểm thử tự động có chi phí bảo trì; cần chọn điểm kiểm tra ổn định và có giá trị.
- **Không xác định người có quyền phê duyệt:** các ví dụ có thể mâu thuẫn nếu không có chủ sở hữu quyết định.
- **Bỏ qua phản hồi sau phát hành:** kiểm thử trước phát hành không thể bao phủ mọi điều kiện sử dụng thực tế.
- **Dùng chỉ số số lượng để thay thế chất lượng:** cần đánh giá khả năng phát hiện lỗi, độ tin cậy và thời gian phản hồi.

## 12. Checklist áp dụng

- [ ] Nhóm hiểu mục tiêu người dùng và rủi ro cần kiểm soát.
- [ ] Các bên liên quan đã cùng làm rõ ví dụ và thuật ngữ nghiệp vụ.
- [ ] Tiêu chí chấp nhận được thống nhất trước khi triển khai.
- [ ] Nguồn xác nhận kết quả mong đợi và người phê duyệt đã rõ.
- [ ] Người phát triển dùng TDD cho logic phù hợp và kiểm thử có phản hồi nhanh.
- [ ] Kịch bản BDD mô tả hành vi, điều kiện và kết quả quan sát được.
- [ ] Kiểm thử ATDD xác minh các điều kiện chấp nhận quan trọng.
- [ ] Kiểm thử được đặt ở cấp phù hợp: đơn vị, API, tích hợp hoặc đầu cuối.
- [ ] Pipeline trả kết quả đủ nhanh và dễ chẩn đoán.
- [ ] Kiểm thử phi chức năng và rủi ro vận hành được xem xét riêng.
- [ ] Kết quả sau phát hành được dùng để cập nhật ví dụ và chiến lược.

## 13. Mối liên hệ tổng thể

~~~mermaid
flowchart TD
    A["Nhu cầu và rủi ro người dùng"]
    B["BDD<br/>Khám phá hành vi bằng ví dụ"]
    C["ATDD<br/>Thống nhất tiêu chí chấp nhận"]
    D["TDD<br/>Phát triển từng hành vi nhỏ"]
    E["Kiểm thử tích hợp và chấp nhận"]
    F["Phát hành, quan sát và phản hồi"]
    A --> B --> C --> D --> E --> F
    F -. "Bài học cho yêu cầu và ví dụ" .-> B
    E -. "Khoảng trống tiêu chí" .-> C
    D -. "Lỗi logic" .-> D
~~~

TDD, BDD và ATDD tạo ra những vòng phản hồi ở các cấp khác nhau. BDD giúp các bên hiểu cùng một hành vi; ATDD xác định điều kiện để chấp nhận chức năng; TDD giúp người phát triển xây dựng logic nhỏ với phản hồi nhanh. Khi được kết nối với kiểm thử tích hợp, kiểm thử phi chức năng và theo dõi sau phát hành, chúng tạo nên chiến lược phản hồi liên tục trong suốt vòng đời phát triển.
