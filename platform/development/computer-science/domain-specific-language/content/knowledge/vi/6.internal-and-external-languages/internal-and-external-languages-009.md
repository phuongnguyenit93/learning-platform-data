# Khi nào nên chọn cách nào?

## 1. Nội bộ và bên ngoài là hai cách xây dựng DSL

Ngôn ngữ chuyên biệt miền (Domain-Specific Language — DSL) có thể được xây dựng theo hai hướng chính: **DSL nội bộ (internal DSL)** và **DSL bên ngoài (external DSL)**.

DSL nội bộ được xây dựng bên trong một ngôn ngữ lập trình có sẵn. Người dùng viết mô tả miền bằng cú pháp của ngôn ngữ chủ và một API được thiết kế để câu lệnh gần với cách diễn đạt nghiệp vụ. Cách này thường được gọi là embedded DSL.

DSL bên ngoài có cú pháp và ngữ pháp riêng, độc lập với cú pháp của một ngôn ngữ lập trình chủ. Người dùng viết mô tả trong file hoặc vùng văn bản theo ngôn ngữ đó; hệ thống dùng lexer, parser và các bước phân tích tiếp theo để hiểu nội dung.

Ví dụ, một DSL nội bộ có thể dùng API Java dạng fluent:

~~~java
Policy policy = policy("Member discount")
    .when(customer().tier().atLeast(GOLD))
    .and(order().total().atLeast(money(2_000_000, VND)))
    .then(applyDiscount(percent(10)));
~~~

Một DSL bên ngoài có thể diễn đạt cùng ý tưởng bằng cú pháp riêng:

~~~text
policy "Member discount"
  when customer.tier >= GOLD
   and order.total >= 2000000 VND
  then discount 10 percent
~~~

Hai đoạn trên chỉ minh họa cách diễn đạt, chưa xác định đầy đủ quy tắc tiền tệ, cách tính tổng đơn hàng hoặc thời điểm đánh giá hạng thành viên. Điểm khác biệt chính nằm ở nơi cú pháp được định nghĩa và công cụ nào chịu trách nhiệm phân tích nó.

Không có lựa chọn nào luôn tốt hơn. Quyết định phụ thuộc vào người sẽ viết DSL, độ phức tạp của miền, yêu cầu cú pháp, công cụ phát triển, cách triển khai và chi phí bảo trì.

## 2. DSL nội bộ hoạt động như thế nào?

DSL nội bộ sử dụng cú pháp hợp lệ của ngôn ngữ chủ, thường thông qua các hàm, method chaining, builder, lambda, annotation hoặc các kiểu dữ liệu chuyên biệt. Compiler của ngôn ngữ chủ vẫn phân tích cú pháp; API DSL định nghĩa những thao tác nào có ý nghĩa trong miền.

Ví dụ Java với builder:

~~~java
Rule rule = rule("Eligible customer")
    .condition(customerTier().isAtLeast(GOLD))
    .condition(orderTotal().isGreaterThanOrEqualTo(
        Money.of(2_000_000, Currency.VND)
    ))
    .action(discountPercent(10));
~~~

Các lời gọi như rule, condition, customerTier và discountPercent là API do ứng dụng cung cấp. Người dùng không tạo một grammar độc lập; họ kết hợp các thành phần mà ngôn ngữ chủ cho phép.

### 2.1 Các kỹ thuật thường dùng

- **Fluent API:** thiết kế tên hàm và chuỗi lời gọi để biểu đạt gần với câu nghiệp vụ.
- **Builder:** tạo cấu trúc nhiều phần theo từng bước, thường có kiểm tra dữ liệu bắt buộc.
- **Lambda:** cho phép truyền một khối biểu thức hoặc hành động để mô tả điều kiện và xử lý.
- **Kiểu dữ liệu miền:** tạo các kiểu như Money, CustomerTier, Duration hoặc OrderStatus để giới hạn giá trị hợp lệ.
- **Annotation hoặc metadata:** bổ sung thông tin khai báo mà framework có thể đọc và xử lý.
- **Operator overloading:** ở ngôn ngữ hỗ trợ, dùng toán tử quen thuộc để biểu đạt phép toán miền. Cần cẩn thận vì ý nghĩa có thể khó nhận ra nếu quá khác thông lệ.

Không phải DSL nội bộ nào cũng cần tất cả kỹ thuật trên. API nhỏ với kiểu dữ liệu rõ ràng thường dễ học và bảo trì hơn một bộ DSL quá nhiều lớp trừu tượng.

### 2.2 Ưu điểm

**Tận dụng compiler và hệ sinh thái của ngôn ngữ chủ.** Người dùng có thể dùng IDE, kiểm tra kiểu, tự động hoàn thành, điều hướng mã, refactor và công cụ debug sẵn có.

**Tích hợp trực tiếp với chương trình.** DSL có thể dùng đối tượng, thư viện, dependency injection, transaction hoặc API của ứng dụng mà không cần tạo một giao thức tích hợp mới.

**Dễ bắt đầu với nhóm phát triển quen ngôn ngữ chủ.** Không cần xây lexer, parser, grammar và hệ thống lỗi riêng nếu cú pháp hiện tại đáp ứng nhu cầu.

**Có thể kiểm tra nhiều lỗi sớm.** Hệ thống kiểu và compiler của ngôn ngữ chủ phát hiện lỗi cú pháp, tên hàm, kiểu đối số và một số lỗi cấu trúc ngay khi build.

**Dễ tái sử dụng thành phần có sẵn.** Thư viện của ngôn ngữ chủ có thể xử lý collection, ngày giờ, số học hoặc kết nối hệ thống.

### 2.3 Hạn chế

**Cú pháp bị giới hạn bởi ngôn ngữ chủ.** Nếu ngôn ngữ chủ yêu cầu dấu ngoặc, dấu chấm phẩy hoặc cấu trúc biểu thức không giống cách chuyên gia nghiệp vụ diễn đạt, DSL có thể trông vẫn như mã lập trình.

**Người dùng cần biết ngôn ngữ chủ.** Một chuyên gia nghiệp vụ không quen Java, Kotlin hoặc Python có thể khó đọc và sửa DSL nội bộ dù API được đặt tên thân thiện.

**Có nguy cơ lộ chi tiết kỹ thuật.** Nếu API yêu cầu người dùng tạo object, truyền callback hoặc hiểu generic type, mô tả nghiệp vụ có thể bị pha trộn với cách triển khai.

**Khó kiểm soát một số hành vi của ngôn ngữ chủ.** Người dùng có thể gọi hàm tùy ý, tạo vòng lặp hoặc truy cập tài nguyên ngoài ý muốn nếu API không giới hạn phạm vi.

**Khả năng tương thích gắn với phiên bản ngôn ngữ và thư viện.** Nâng cấp compiler hoặc thay đổi API có thể làm các mô tả cũ không biên dịch được.

## 3. DSL bên ngoài hoạt động như thế nào?

DSL bên ngoài định nghĩa cú pháp riêng. Hệ thống thường đọc văn bản nguồn, phân tích thành token, xây dựng cây cú pháp, kiểm tra ngữ nghĩa rồi chuyển thành mô hình hoặc hành động.

Ví dụ một file chính sách:

~~~text
policy "Member discount" {
  eligibility:
    customer.tier >= GOLD
    and order.total >= 2000000 VND

  benefit:
    discount 10 percent
}
~~~

Người viết chỉ cần học từ vựng và quy tắc của ngôn ngữ này. Họ không cần biết cấu trúc class hoặc method của Java. Đổi lại, nhóm phát triển phải định nghĩa grammar, parser, mô hình ngữ nghĩa, công cụ báo lỗi và cách kết nối với hệ thống thực thi.

### 3.1 Các thành phần thường có

1. **Đặc tả cú pháp:** mô tả token, từ khóa, biểu thức và cấu trúc hợp lệ.
2. **Lexer:** chia văn bản thành các token như identifier, string, number, keyword và operator.
3. **Parser:** kiểm tra thứ tự token và tạo AST.
4. **Phân tích ngữ nghĩa:** kiểm tra tên, kiểu, phạm vi, tham chiếu và quy tắc miền.
5. **Biểu diễn trung gian hoặc mô hình miền:** lưu cấu trúc đã được hiểu để có thể kiểm tra, diễn giải hoặc sinh đầu ra.
6. **Backend hoặc interpreter:** chuyển mô hình thành hành vi hoặc định dạng target.
7. **Diagnostics:** báo lỗi, cảnh báo và vị trí trong file nguồn.
8. **Tooling:** hỗ trợ editor, format, validate, completion hoặc tài liệu cho người viết DSL.

Một DSL nhỏ có thể dùng parser đơn giản hoặc parser generator. Khi grammar phức tạp, có nhiều phiên bản hoặc cần trải nghiệm editor tốt, cần đầu tư nhiều hơn vào công cụ và đặc tả.

### 3.2 Ưu điểm

**Tự do thiết kế cú pháp.** Có thể tạo cấu trúc gần với ngôn ngữ nghiệp vụ, không bị ràng buộc bởi dấu câu hoặc quy tắc của một ngôn ngữ lập trình tổng quát.

**Phù hợp với người không phải lập trình viên.** Nếu từ vựng và cấu trúc rõ ràng, chuyên gia nghiệp vụ có thể đọc hoặc chỉnh sửa mô tả mà không cần hiểu Java hay Python.

**Kiểm soát phạm vi biểu đạt.** Grammar chỉ cho phép các cấu trúc được thiết kế. Điều này giúp giới hạn khả năng thực thi tùy ý và tạo ra một giao diện khai báo có thể kiểm tra.

**Có thể độc lập với công nghệ triển khai.** Cùng một ngôn ngữ nguồn có thể được diễn giải trong ứng dụng, sinh Java, sinh SQL hoặc xuất cấu hình nếu ngữ nghĩa được thiết kế phù hợp.

**Có thể lưu trữ và trao đổi như tài liệu.** Các file DSL có thể được version control, review, so sánh và chuyển giữa các hệ thống.

### 3.3 Hạn chế

**Chi phí xây dựng và bảo trì cao hơn.** Nhóm phải thiết kế grammar, parser, semantic analyzer, thông báo lỗi và thường cả công cụ editor.

**Phải tự xây trải nghiệm phát triển.** Tự động hoàn thành, điều hướng định nghĩa, rename symbol, format và debug không tự xuất hiện như trong ngôn ngữ chủ.

**Lỗi có thể khó giải thích.** Một câu có thể đúng cú pháp nhưng sai ngữ nghĩa; cần chỉ rõ vị trí và lý do để người dùng sửa được.

**Cần quản lý phiên bản ngôn ngữ.** Thay đổi grammar hoặc ý nghĩa có thể làm file DSL cũ không còn hợp lệ hoặc cho kết quả khác.

**Tích hợp runtime cần thiết kế rõ.** DSL thường cần truy cập dữ liệu, dịch vụ hoặc quyền của ứng dụng. Cần định nghĩa API và giới hạn an toàn thay vì để file DSL truy cập tùy ý.

## 4. So sánh hai cách

| Tiêu chí | DSL nội bộ | DSL bên ngoài |
|---|---|---|
| Cú pháp | Dựa trên ngôn ngữ chủ | Grammar riêng |
| Công cụ phân tích | Compiler của ngôn ngữ chủ | Lexer/parser và semantic analyzer riêng |
| Người viết phù hợp | Lập trình viên hoặc người biết ngôn ngữ chủ | Người dùng được đào tạo về cú pháp miền, kể cả chuyên gia nghiệp vụ |
| IDE | Tận dụng tooling sẵn có | Cần plugin hoặc tooling riêng nếu muốn trải nghiệm tốt |
| Tích hợp code | Trực tiếp với API và kiểu của ứng dụng | Qua model, IR, interpreter hoặc backend |
| Khả năng giới hạn biểu đạt | Phụ thuộc API và khả năng ngôn ngữ chủ | Có thể giới hạn bằng grammar và semantic rules |
| Tự do thiết kế ngôn ngữ | Hạn chế bởi cú pháp chủ | Cao hơn |
| Chi phí ban đầu | Thường thấp hơn | Thường cao hơn |
| Kiểm soát phiên bản | Gắn với compiler và API chủ | Có thể quản lý phiên bản DSL riêng |
| Tính di động | Thường gắn với hệ sinh thái ngôn ngữ chủ | Có thể độc lập hơn nếu định nghĩa và runtime ổn định |
| Khả năng tiếp cận người nghiệp vụ | Phụ thuộc mức độ quen ngôn ngữ chủ | Có thể tốt hơn nếu ngôn ngữ được thiết kế phù hợp |

Không nên đánh giá chỉ dựa trên độ ngắn của cú pháp. Một DSL bên ngoài có thể trông rất dễ đọc nhưng khó cài đặt, debug và bảo trì. Một DSL nội bộ có thể dài hơn nhưng mang lại kiểm tra kiểu và tích hợp tốt. Cần đánh giá cả người viết, người đọc, người vận hành và người chịu trách nhiệm phát triển.

## 5. Khi nào nên chọn DSL nội bộ?

DSL nội bộ thường phù hợp trong các tình huống sau.

### 5.1 Người dùng chính là lập trình viên

Nếu người viết DSL là đội phát triển đã quen với ngôn ngữ chủ, việc yêu cầu họ dùng một API khai báo thường không tạo thêm rào cản đáng kể.

Ví dụ, một framework Java cho phép lập trình viên khai báo pipeline kiểm tra:

~~~java
Pipeline pipeline = pipeline()
    .step(validateInput())
    .step(checkPermission())
    .step(calculatePrice())
    .step(persistResult());
~~~

Các thành phần vẫn là API Java, nhưng cấu trúc gọi thể hiện rõ một pipeline trong miền.

### 5.2 DSL cần tích hợp sâu với ứng dụng

Nếu mô tả thường xuyên dùng object, service, transaction hoặc thư viện hiện có, DSL nội bộ giúp gọi các thành phần đó trực tiếp.

Ví dụ, một DSL cấu hình kiểm thử có thể dùng fixture, mock và assertion của framework hiện tại. Xây parser riêng chỉ để chuyển các câu lệnh đó thành lời gọi API có thể làm tăng chi phí mà không đem lại lợi ích rõ ràng.

### 5.3 Cú pháp của ngôn ngữ chủ đã đủ biểu đạt

Nếu bài toán chủ yếu là kết hợp điều kiện, cấu hình pipeline hoặc khai báo builder, cú pháp của Java, Kotlin, Python hay ngôn ngữ chủ khác có thể đã đủ rõ.

Khi đó, một API có tên miền tốt và kiểu dữ liệu chặt chẽ có thể đáp ứng nhu cầu mà không cần grammar riêng.

### 5.4 Cần tận dụng tooling sẵn có

Khi kiểm tra kiểu, refactor, tự động hoàn thành và debug là yêu cầu quan trọng, DSL nội bộ có lợi thế vì IDE hiểu trực tiếp ngôn ngữ chủ.

Điều này đặc biệt hữu ích khi DSL thay đổi cùng mã nguồn và được review trong cùng quy trình build.

### 5.5 Phạm vi DSL nhỏ và ổn định

Nếu chỉ có một số cấu trúc khai báo, ít thay đổi và người dùng đều là lập trình viên, xây parser và tooling riêng có thể không đáng với chi phí duy trì.

DSL nội bộ cũng phù hợp khi API có thể phát triển cùng ứng dụng và không cần trao đổi độc lập với các hệ thống khác.

## 6. Khi nào nên chọn DSL bên ngoài?

DSL bên ngoài thường phù hợp trong các tình huống sau.

### 6.1 Người viết không nên phải biết ngôn ngữ lập trình chủ

Nếu người dùng chính là chuyên viên vận hành, chuyên gia nghiệp vụ, nhà phân tích hoặc quản trị viên chính sách, yêu cầu họ viết Java hoặc Python có thể không phù hợp.

Một ngôn ngữ riêng với từ vựng nghiệp vụ, thông báo lỗi rõ và cú pháp có giới hạn có thể giúp họ tự quản lý mô tả.

### 6.2 Cần cú pháp gần với ngôn ngữ nghiệp vụ

Một số miền có thuật ngữ và cấu trúc diễn đạt rất đặc thù. Nếu cú pháp ngôn ngữ chủ buộc người dùng phải viết nhiều wrapper hoặc biểu thức khó đọc, grammar riêng có thể diễn đạt ý định rõ hơn.

Ví dụ, chuyên viên chính sách có thể cần mô tả:

~~~text
approve request when
  applicant is verified
  and requested_amount is within daily_limit
otherwise require manual_review
~~~

Người dùng có thể hiểu câu này theo ngôn ngữ nghiệp vụ mà không cần biết class hoặc lambda.

### 6.3 Cần giới hạn những gì người dùng được phép làm

Nếu file cấu hình hoặc chính sách do nhiều người tạo, không nên mặc định họ được phép chạy mã tùy ý. DSL bên ngoài có thể chỉ cho phép một tập biểu thức, hàm và thao tác được duyệt.

Tuy vậy, grammar riêng không tự động bảo đảm an toàn. Interpreter và backend vẫn phải kiểm tra quyền, giới hạn tài nguyên, truy cập dữ liệu và hành động được phép.

### 6.4 Mô tả cần độc lập với ngôn ngữ lập trình

Nếu file DSL cần được dùng trong nhiều ứng dụng hoặc nhiều công nghệ, một định dạng độc lập có thể tạo hợp đồng ổn định hơn API gắn với Java hay Python.

Ví dụ, chính sách có thể được viết một lần rồi được ứng dụng Java diễn giải, công cụ kiểm tra xuất báo cáo và backend khác chuyển thành cấu hình cho hệ thống thực thi.

### 6.5 Cần quản lý file như tài sản nghiệp vụ

Khi các mô tả cần được lưu, review, phê duyệt, so sánh phiên bản hoặc chuyển giao giữa các nhóm, file DSL riêng có thể thuận tiện hơn mã nguồn nhúng trong ứng dụng.

Nhóm có thể tổ chức thư mục, phân quyền, quy trình phê duyệt và lịch sử thay đổi theo từng chính sách hoặc quy trình.

### 6.6 Grammar và ngữ nghĩa là một phần quan trọng của sản phẩm

Nếu cú pháp, từ vựng, phiên bản và trải nghiệm chỉnh sửa chính là một phần giá trị mà sản phẩm cung cấp, đầu tư vào DSL bên ngoài có thể hợp lý. Trong trường hợp này, parser và tooling không chỉ là chi phí phụ mà là thành phần sản phẩm.

## 7. Các tiêu chí cần cân nhắc trước khi quyết định

Không nên chọn theo sở thích của đội kỹ thuật. Hãy thu thập bằng chứng về cách DSL sẽ được dùng.

### 7.1 Người dùng và kỹ năng

Hãy xác định:

- Ai tạo mô tả?
- Ai đọc, review và phê duyệt?
- Người dùng có biết ngôn ngữ chủ không?
- Họ có cần chỉnh sửa trực tiếp trong IDE không?
- Bao nhiêu nhóm hoặc vai trò sẽ sử dụng DSL?

Nếu người dùng chủ yếu là lập trình viên, DSL nội bộ thường dễ tiếp cận. Nếu nhiều chuyên gia nghiệp vụ cần tự chỉnh sửa, DSL bên ngoài đáng được xem xét.

### 7.2 Độ phức tạp của miền

Đánh giá số lượng khái niệm, quy tắc, biểu thức, cấu trúc lồng nhau, kiểu dữ liệu và ngoại lệ.

Một DSL chỉ mô tả vài điều kiện có thể dùng builder API. Một DSL có nhiều cấu trúc nghiệp vụ, cú pháp riêng, tham chiếu và quy tắc phạm vi có thể cần grammar và semantic analyzer độc lập.

Độ phức tạp lớn không tự động đồng nghĩa với DSL bên ngoài. Một API nội bộ có thể vẫn phù hợp nếu người dùng là lập trình viên và ngôn ngữ chủ biểu đạt tốt. Tương tự, một DSL bên ngoài nhỏ vẫn có thể hữu ích nếu người dùng không biết ngôn ngữ chủ.

### 7.3 Yêu cầu cú pháp và trải nghiệm viết

Hỏi xem người dùng cần:

- Câu lệnh gần ngôn ngữ tự nhiên hay cấu trúc khai báo ngắn?
- Tự động hoàn thành và kiểm tra ngay khi nhập?
- Thông báo lỗi theo thuật ngữ nghiệp vụ?
- Comment, format và tài liệu trong file?
- Khả năng viết nhiều biểu thức và tái sử dụng thành phần?

Nếu cần cú pháp rất đặc thù, DSL bên ngoài có lợi thế. Nếu cú pháp hiện tại đã đủ rõ và IDE hỗ trợ tốt, DSL nội bộ có thể đơn giản hơn.

### 7.4 Tích hợp và môi trường chạy

Xác định DSL có cần truy cập trực tiếp object và service của ứng dụng không, hay chỉ cần mô tả độc lập rồi gửi qua một API hoặc IR.

Tích hợp sâu với một ứng dụng thường thuận lợi cho DSL nội bộ. Cần trao đổi giữa nhiều hệ thống hoặc nhiều target thường làm DSL bên ngoài hấp dẫn hơn, nhưng vẫn có thể dùng API nội bộ làm một frontend khác cho cùng mô hình.

### 7.5 Bảo mật và quyền hạn

Nếu người dùng không được phép chạy mã tùy ý, cần xem cách giới hạn hành động.

DSL nội bộ có thể vô tình mở toàn bộ khả năng của ngôn ngữ chủ nếu API để lộ object hoặc callback tùy ý. DSL bên ngoài có thể giới hạn grammar nhưng vẫn cần kiểm soát interpreter, backend và dữ liệu truy cập.

Hãy xác định:

- Danh sách hàm và thao tác được phép.
- Quyền truy cập dữ liệu theo người dùng.
- Có cho phép truy cập mạng, file hoặc hệ thống bên ngoài không.
- Giới hạn thời gian, bộ nhớ và số lần gọi.
- Cách audit và truy nguyên hành động.

### 7.6 Chi phí phát triển và bảo trì

So sánh chi phí toàn vòng đời:

- Thiết kế API hoặc grammar.
- Xây parser và semantic analyzer nếu cần.
- Tích hợp IDE, format và diagnostics.
- Viết tài liệu và đào tạo.
- Quản lý phiên bản và migration.
- Hỗ trợ người dùng và xử lý lỗi.
- Tích hợp build, deploy và runtime.

DSL nội bộ thường giảm chi phí ban đầu nhờ tận dụng ngôn ngữ chủ. DSL bên ngoài cần đầu tư nhiều hơn, nhưng có thể giảm chi phí vận hành khi người dùng nghiệp vụ có thể tự quản lý chính sách mà không cần yêu cầu lập trình viên sửa code cho mọi thay đổi.

### 7.7 Độ ổn định và tần suất thay đổi

Nếu mô tả thay đổi cùng chu kỳ phát hành phần mềm, DSL nội bộ có thể phù hợp. Nếu chính sách thay đổi thường xuyên và cần nạp lại mà không triển khai ứng dụng, DSL bên ngoài kết hợp với interpreter hoặc backend phù hợp có thể thuận tiện.

Tuy nhiên, khả năng thay đổi động phụ thuộc vào kiến trúc runtime, không chỉ vào loại cú pháp. Một DSL nội bộ cũng có thể được lưu dưới dạng cấu hình và nạp động; một DSL bên ngoài cũng có thể cần biên dịch và triển khai lại.

### 7.8 Khả năng di động và nhiều target

Nếu cùng một mô tả cần chạy trên nhiều nền tảng, một ngôn ngữ độc lập với target có thể giúp giữ hợp đồng chung. Cần cân nhắc IR và backend để tránh mỗi target hiểu ngữ nghĩa khác nhau.

Nếu chỉ chạy trong một ứng dụng và phụ thuộc chặt vào API của ứng dụng, DSL nội bộ có thể tự nhiên hơn.

## 8. Bảng gợi ý lựa chọn

Bảng sau dùng để định hướng thảo luận, không phải công thức chấm điểm tuyệt đối:

| Bối cảnh | Lựa chọn thường phù hợp hơn | Lý do |
|---|---|---|
| Chỉ lập trình viên tạo và đọc mô tả | Nội bộ | Tận dụng ngôn ngữ và IDE sẵn có |
| Chuyên viên nghiệp vụ cần tự sửa chính sách | Bên ngoài | Có thể dùng cú pháp và thuật ngữ riêng |
| Mô tả gọi sâu vào API ứng dụng | Nội bộ | Tích hợp trực tiếp với kiểu và object |
| Cần file độc lập để review và trao đổi | Bên ngoài | Có định dạng và vòng đời riêng |
| Cấu trúc chỉ gồm vài bước khai báo | Nội bộ | API builder có thể đủ dùng |
| Cần grammar phong phú và cú pháp riêng | Bên ngoài | Chủ động thiết kế cú pháp |
| Cần giới hạn tập hành động người dùng | Bên ngoài thường thuận lợi | Grammar có thể chỉ cho phép cấu trúc đã định nghĩa |
| Cần tận dụng compiler và tooling chủ | Nội bộ | Giảm công xây dựng công cụ |
| Cùng mô tả cần nhiều backend | Bên ngoài thường thuận lợi | Có thể dùng một nguồn độc lập và nhiều backend |
| Thay đổi thường xuyên do người nghiệp vụ quản lý | Bên ngoài thường thuận lợi | Tách file chính sách khỏi mã nguồn ứng dụng |

Các từ “thường phù hợp hơn” rất quan trọng. Mỗi dự án cần xác nhận bằng người dùng, kịch bản thực tế và nguyên mẫu nhỏ.

## 9. Quy trình ra quyết định

Có thể dùng quy trình sau để chọn hướng thiết kế.

### Bước 1: Xác định người tạo và người đọc

Ghi rõ vai trò, kỹ năng và tần suất sử dụng. Nếu người dùng không biết ngôn ngữ chủ, đừng mặc định họ có thể học một API nội bộ chỉ vì API đó dễ viết với lập trình viên.

### Bước 2: Thu thập ví dụ mô tả thật

Chọn một số chính sách hoặc quy trình cần diễn đạt. Thử viết chúng bằng ngôn ngữ chủ hiện tại và quan sát xem câu lệnh có rõ, ngắn, kiểm tra được và dễ review không.

Nếu API nội bộ cần nhiều lớp wrapper, lambda lồng nhau hoặc cú pháp khó hiểu, đó là tín hiệu cần xem xét grammar riêng.

### Bước 3: Đánh giá yêu cầu độc lập

Hỏi file mô tả có cần được lưu, trao đổi, phê duyệt hoặc chạy ngoài ứng dụng chủ không. Nếu cần, xem xét DSL bên ngoài hoặc một định dạng khai báo riêng.

### Bước 4: Đánh giá mức kiểm soát và an toàn

Xác định người dùng được phép khai báo những hành động nào. Nếu chỉ cần chọn trong một tập quy tắc giới hạn, hãy thiết kế ngôn ngữ hoặc API không cho phép truy cập tùy ý.

### Bước 5: Ước lượng chi phí toàn vòng đời

Tính cả parser, tooling, tài liệu, đào tạo, migration và hỗ trợ. Với DSL nội bộ, tính cả chi phí người nghiệp vụ phải nhờ lập trình viên chỉnh sửa mô tả.

### Bước 6: Tạo nguyên mẫu nhỏ

Chọn một tình huống đại diện và triển khai một phiên bản tối thiểu theo hướng phù hợp nhất. Nếu còn phân vân, thử cả hai hướng với cùng ví dụ để so sánh khả năng đọc, viết, kiểm tra và tích hợp.

### Bước 7: Đánh giá với người dùng thật

Cho người sẽ viết và review DSL thử thực hiện công việc. Ghi nhận thời gian, lỗi, câu hỏi, mức độ hiểu và khả năng tự sửa. Đừng chỉ hỏi họ thích cú pháp nào; hãy quan sát họ có hoàn thành nhiệm vụ chính xác không.

### Bước 8: Chốt quyết định và điều kiện xem xét lại

Ghi lại lý do chọn, giả định, rủi ro và những thay đổi có thể khiến quyết định cần xem xét lại. Ví dụ, nếu sau này chuyên viên nghiệp vụ cần tự quản lý chính sách, API nội bộ có thể không còn phù hợp.

## 10. Ví dụ quyết định trong ba bối cảnh

### 10.1 Pipeline kiểm thử trong nhóm phát triển

Một nhóm Java muốn mô tả các bước chuẩn bị dữ liệu, gọi API và kiểm tra kết quả. Người viết đều là lập trình viên; pipeline cần truy cập trực tiếp fixture, HTTP client và assertion của framework.

DSL nội bộ thường là lựa chọn hợp lý:

~~~java
scenario("Create customer")
    .given(customerPayload())
    .when(post("/customers"))
    .then(statusIs(201))
    .and(responseHas("id"));
~~~

Ngôn ngữ Java và IDE hỗ trợ kiểm tra tên hàm, kiểu dữ liệu và refactor. Một grammar bên ngoài có thể tạo thêm parser và công cụ mà chưa đem lại lợi ích tương xứng.

### 10.2 Chính sách xét duyệt do chuyên viên vận hành quản lý

Một tổ chức có nhiều chuyên viên vận hành cần điều chỉnh ngưỡng phê duyệt theo loại yêu cầu. Họ không viết mã và cần xem lại file chính sách trước khi kích hoạt.

DSL bên ngoài có thể phù hợp:

~~~text
approval "Standard request"
  when amount <= 5000000 VND
  require applicant.status == ACTIVE
  decision approve

approval "High value request"
  when amount > 5000000 VND
  decision require_manager
~~~

Hệ thống có thể parse file, kiểm tra kiểu và quyền, cho người có thẩm quyền review rồi mới kích hoạt. Cần quy định rõ thứ tự chính sách, trường hợp không có quy tắc phù hợp và cách xử lý khi hai quy tắc cùng khớp.

### 10.3 Thư viện truy vấn cho nhiều ứng dụng

Một nhóm phát triển cần tạo điều kiện lọc dữ liệu có thể tái sử dụng giữa nhiều dịch vụ Java. Nếu người dùng đều là lập trình viên và cần ghép điều kiện với object model của ứng dụng, một DSL nội bộ có thể thuận lợi:

~~~java
Predicate<Customer> eligible =
    customer -> customer.isActive()
        && customer.getTier().atLeast(GOLD);
~~~

Nếu sau này các điều kiện cần được quản trị viên chỉnh sửa hoặc chuyển thành truy vấn trên nhiều hệ quản trị, nhóm có thể tách mô hình điều kiện thành biểu diễn trung gian và cung cấp thêm frontend hoặc backend. Không nhất thiết phải xây DSL bên ngoài ngay từ đầu nếu nhu cầu chưa xuất hiện.

## 11. Có thể kết hợp DSL nội bộ và bên ngoài không?

Có. Hai cách không nhất thiết loại trừ nhau. Một hệ thống có thể cung cấp nhiều cách nhập mô tả nhưng chuyển chúng về cùng mô hình miền hoặc IR.

Ví dụ:

~~~text
DSL nội bộ Java --------+
                        |
DSL bên ngoài ----------+--> Domain Model / IR
                        |          |
Builder API ------------+          +--> Interpreter
                                   +--> Java backend
                                   +--> SQL backend
~~~

Một frontend nội bộ có thể phục vụ lập trình viên; frontend bên ngoài phục vụ chuyên viên nghiệp vụ. Cả hai dùng chung semantic analyzer và backend nếu cùng ngữ nghĩa.

### 11.1 Khi nào cách kết hợp có ích?

- Có nhiều nhóm người dùng với kỹ năng khác nhau.
- Cần API lập trình để tạo mô tả tự động và file DSL để chỉnh sửa thủ công.
- Muốn chuyển dần từ cấu hình cũ sang ngôn ngữ mới.
- Cần một mô hình chung để hỗ trợ nhiều target.
- Cần giữ khả năng nhúng trong ứng dụng nhưng vẫn trao đổi mô tả độc lập.

### 11.2 Điều kiện để kết hợp không trở nên phức tạp

Hai frontend phải thống nhất:

- Từ vựng và định nghĩa khái niệm.
- Kiểu dữ liệu và quy tắc chuyển đổi.
- Ý nghĩa của biểu thức và toán tử.
- Quy tắc lỗi và giá trị không xác định.
- Phiên bản ngữ nghĩa.
- Cách xác thực và phân quyền.

Nếu Java API cho phép một thao tác mà grammar bên ngoài không thể biểu diễn, cần quyết định đó là phần mở rộng riêng hay cần bổ sung vào mô hình chung. Không nên để hai frontend âm thầm tạo ra hai ngôn ngữ khác nhau dù dùng cùng tên miền.

## 12. Chuyển đổi từ hướng này sang hướng khác

Nhu cầu có thể thay đổi theo thời gian. Một DSL nội bộ ban đầu có thể trở nên khó dùng khi người nghiệp vụ cần tự chỉnh sửa; một DSL bên ngoài có thể trở nên quá tốn kém khi chỉ còn nhóm phát triển sử dụng.

### 12.1 Từ nội bộ sang bên ngoài

Có thể thực hiện theo các bước:

1. Tách mô hình miền khỏi các lời gọi API cụ thể.
2. Xác định tập biểu thức và cấu trúc cần được biểu diễn.
3. Định nghĩa grammar và quy tắc ngữ nghĩa tương đương.
4. Viết parser chuyển file DSL thành cùng mô hình hoặc IR.
5. Dùng lại interpreter hoặc backend hiện có nếu hợp đồng phù hợp.
6. Chạy song song trên các ví dụ đã xác nhận và so sánh kết quả.
7. Hướng dẫn người dùng và quản lý phiên bản file.

Không nên cố chuyển từng dòng Java sang cú pháp mới một cách máy móc. Trước hết phải xác định phần nào là quy tắc nghiệp vụ, phần nào là chi tiết lập trình hoặc tích hợp.

### 12.2 Từ bên ngoài sang nội bộ

Nếu chỉ lập trình viên còn sử dụng DSL, có thể:

1. Giữ nguyên mô hình ngữ nghĩa hoặc IR.
2. Tạo API builder tương ứng với các cấu trúc thực sự cần dùng.
3. Viết bộ chuyển đổi từ API sang cùng mô hình.
4. Duy trì đọc file cũ trong giai đoạn chuyển tiếp nếu cần.
5. Kiểm tra kết quả tương đương trước khi ngừng frontend cũ.

Không nên loại bỏ file DSL cũ trước khi xác định chính sách lưu trữ, khả năng tái tạo và nhu cầu audit.

## 13. Những hiểu lầm cần tránh

### DSL nội bộ chỉ là một API có tên hàm đẹp

Một API được thiết kế tốt có thể tạo trải nghiệm DSL nội bộ, nhưng vẫn cần có mô hình miền, quy tắc và giới hạn biểu đạt rõ ràng. Đổi tên hàm mà không làm rõ ngữ nghĩa không tạo ra một DSL hữu ích.

### DSL bên ngoài luôn dễ cho người nghiệp vụ

Cú pháp riêng không tự động dễ học. Nếu dùng nhiều ký hiệu, thuật ngữ không thống nhất hoặc lỗi khó hiểu, người nghiệp vụ vẫn cần hỗ trợ kỹ thuật.

### DSL bên ngoài luôn an toàn

Parser chỉ kiểm tra cú pháp. Interpreter hoặc backend vẫn có thể thực thi thao tác nguy hiểm nếu không giới hạn quyền và tài nguyên.

### DSL nội bộ không thể thay đổi động

Một DSL nội bộ có thể tạo cấu trúc dữ liệu hoặc biểu thức được lưu và nạp động. Khả năng thay đổi phụ thuộc vào cách thiết kế runtime và API, không chỉ vào việc dùng ngôn ngữ chủ.

### Chỉ có thể chọn một loại cho toàn bộ hệ thống

Một hệ thống có thể có frontend nội bộ, file DSL bên ngoài và nhiều backend dùng chung IR. Điều quan trọng là giữ một hợp đồng ngữ nghĩa nhất quán.

### Hiệu năng quyết định trực tiếp loại DSL

DSL nội bộ không mặc nhiên nhanh hơn DSL bên ngoài. Parser, interpreter, code generator, tối ưu hóa và runtime mới quyết định phần lớn chi phí thực thi. Cần đo trên workload thực tế trước khi chọn kiến trúc vì hiệu năng.

## 14. Hồ sơ quyết định lựa chọn

Khi nhóm chốt hướng DSL, nên lưu một hồ sơ ngắn để người khác hiểu lý do và điều kiện của quyết định:

| Mục | Nội dung |
|---|---|
| Vấn đề cần giải quyết | Công việc hoặc quy tắc cần được mô tả |
| Người tạo | Vai trò và kỹ năng của người viết |
| Người đọc/review | Vai trò chịu trách nhiệm hiểu và phê duyệt |
| Ví dụ đại diện | Một số mô tả thực tế đã thu thập |
| Cú pháp cần thiết | Cấu trúc và thuật ngữ cần có |
| Tích hợp | Object, API, dữ liệu và hệ thống liên quan |
| Mức kiểm soát | Những hành động được phép và bị cấm |
| Lựa chọn | Nội bộ, bên ngoài hoặc kết hợp |
| Lý do | Tiêu chí có trọng số hoặc bằng chứng hỗ trợ |
| Chi phí | Parser, tooling, đào tạo, vận hành và migration |
| Rủi ro | Khả năng khó dùng, sai ngữ nghĩa hoặc phụ thuộc công nghệ |
| Điều kiện xem xét lại | Thay đổi nào sẽ khiến nhóm đánh giá lại quyết định |

Hồ sơ nên ghi các giả định chưa được kiểm chứng. Nếu chưa biết ai sẽ là người viết DSL hoặc tần suất thay đổi chính sách, đó là câu hỏi cần trả lời trước khi đầu tư lớn.

## 15. Câu hỏi tự kiểm tra

1. Phân biệt DSL nội bộ và DSL bên ngoài.
2. Vì sao DSL nội bộ có thể tận dụng kiểm tra kiểu và tooling của ngôn ngữ chủ?
3. Những chi phí nào cần tính khi xây DSL bên ngoài?
4. Khi người dùng chính là chuyên viên nghiệp vụ, những yếu tố nào cần được xem xét?
5. Khi DSL cần tích hợp trực tiếp với object và service của ứng dụng, lựa chọn nào thường thuận lợi?
6. Vì sao grammar riêng không tự động bảo đảm an toàn?
7. Tại sao không nên chỉ dựa vào độ ngắn của cú pháp để quyết định?
8. Khi nào nên kết hợp frontend nội bộ và bên ngoài?
9. Nêu các bước chính khi chuyển từ DSL nội bộ sang DSL bên ngoài.
10. Những điều kiện nào có thể khiến nhóm cần xem xét lại lựa chọn ban đầu?

Khi ra quyết định, hãy dùng các ví dụ thực tế và thử nghiệm với người dùng dự kiến. Chọn cách giúp họ diễn đạt đúng công việc, giúp hệ thống kiểm tra được ý nghĩa và giúp nhóm duy trì ngôn ngữ trong suốt vòng đời sản phẩm.
