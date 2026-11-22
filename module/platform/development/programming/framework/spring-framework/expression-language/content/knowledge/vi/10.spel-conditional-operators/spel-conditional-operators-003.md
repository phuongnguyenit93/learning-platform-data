# Khác biệt giữa Elvis và điều kiện ba ngôi đầy đủ

SpEL có hai toán tử thường được dùng để chọn giá trị thay thế: Elvis và điều kiện ba ngôi đầy đủ. Cả hai đều có thể xuất hiện trong cấu hình hoặc trong biểu thức đánh giá lúc chạy, nhưng chúng giải quyết hai nhu cầu khác nhau.

- **Elvis** viết ngắn gọn quy tắc “dùng giá trị mặc định nếu biểu thức bên trái là null hoặc chuỗi rỗng”.
- **Điều kiện ba ngôi** chọn một trong hai biểu thức dựa trên kết quả true/false của một điều kiện do ứng dụng xác định.

Hiểu đúng khác biệt này giúp tránh việc vô tình thay thế các giá trị hợp lệ như false hoặc 0, đồng thời giúp biểu thức thể hiện đúng ý định nghiệp vụ.

## 1. Điều kiện ba ngôi đầy đủ

Cú pháp của toán tử điều kiện ba ngôi là:

    condition ? valueWhenTrue : valueWhenFalse

SpEL đánh giá condition trước. Nếu điều kiện là true, biểu thức trả về valueWhenTrue; nếu false, nó trả về valueWhenFalse.

Ví dụ, phân loại kết quả học tập dựa trên điểm:

    #score >= 50 ? 'PASS' : 'RETRY'

Nếu score là 75, kết quả là PASS. Nếu score là 42, kết quả là RETRY. Điều kiện có thể là một biểu thức logic dài hơn:

    #score >= 50 and #attendance >= 0.8
        ? 'PASS'
        : 'REVIEW'

Điều kiện ở đây kết hợp cả điểm và tỷ lệ tham dự. Kết quả chỉ được chọn sau khi toàn bộ điều kiện Boolean được đánh giá.

Toán tử ba ngôi phù hợp khi quyết định phụ thuộc vào một quy tắc cụ thể: ngưỡng, trạng thái, quyền, loại đối tượng hoặc nhiều điều kiện kết hợp. Nó không chỉ dùng để xử lý null; bất kỳ điều kiện Boolean hợp lệ nào cũng có thể điều khiển việc chọn nhánh.

## 2. Toán tử Elvis

Elvis có cú pháp ngắn hơn:

    expression ?: defaultValue

Nếu expression bên trái có giá trị khác null và không phải chuỗi rỗng, SpEL trả về chính giá trị đó. Nếu giá trị bên trái là null hoặc là chuỗi rỗng, SpEL trả về defaultValue.

Ví dụ lấy tên hiển thị:

    #displayName ?: 'Khách vãng lai'

Nếu displayName là An, kết quả là An. Nếu displayName là null hoặc chuỗi rỗng, kết quả là Khách vãng lai.

Nếu viết bằng toán tử ba ngôi đầy đủ, cùng quy tắc sẽ cần lặp lại biểu thức bên trái:

    #displayName != null and #displayName != ''
        ? #displayName
        : 'Khách vãng lai'

Elvis rút gọn đúng mẫu kiểm tra này. Nó đặc biệt tiện khi chỉ muốn cung cấp một giá trị mặc định cho dữ liệu có thể thiếu.

## 3. Elvis không phải phép kiểm tra truthy/falsy

Một điểm dễ nhầm là Elvis không coi mọi giá trị “rỗng” hoặc “sai” theo cách của một số ngôn ngữ lập trình khác. Trong SpEL, điều kiện thay thế của Elvis tập trung vào null và chuỗi rỗng.

Các trường hợp minh họa:

| Giá trị bên trái | Biểu thức | Kết quả |
|---|---|---|
| null | null ?: 'DEFAULT' | DEFAULT |
| Chuỗi rỗng | '' ?: 'DEFAULT' | DEFAULT |
| Chuỗi An | 'An' ?: 'DEFAULT' | An |
| Chuỗi chỉ có dấu cách | ' ' ?: 'DEFAULT' | Giữ nguyên chuỗi dấu cách |
| false | false ?: true | false |
| Số 0 | 0 ?: 10 | 0 |
| List rỗng | {} ?: {1, 2} | Giữ list rỗng |

Vì vậy, Elvis không có nghĩa là “nếu giá trị không có nội dung theo mọi cách thì dùng mặc định”. Nó không tự trim chuỗi, không coi dấu cách là chuỗi rỗng, không coi false là thiếu giá trị, và cũng không thay thế một collection rỗng.

Nếu nghiệp vụ muốn coi chuỗi chỉ chứa khoảng trắng là không hợp lệ, hãy viết điều kiện rõ ràng bằng trim và kiểm tra độ dài, hoặc chuẩn hóa dữ liệu trước khi đánh giá biểu thức.

## 4. So sánh cùng một quy tắc bằng hai cách

Giả sử một ứng dụng hiển thị tên người dùng. Khi tên không có, giao diện cần dùng nhãn mặc định.

Cách viết bằng Elvis:

    #name ?: 'Anonymous'

Cách viết bằng điều kiện ba ngôi đầy đủ:

    #name != null and #name != ''
        ? #name
        : 'Anonymous'

Hai biểu thức có cùng mục tiêu: trả về tên khi có tên hợp lệ theo tiêu chí null/chuỗi rỗng, nếu không thì trả về Anonymous.

Nếu điều kiện thay đổi, toán tử ba ngôi thể hiện rõ quy tắc hơn. Ví dụ, chỉ hiển thị tên khi người dùng đã xác minh:

    #user.verified
        ? #user.name
        : 'Unverified user'

Elvis không thể thay thế biểu thức trên vì quyết định phụ thuộc vào thuộc tính verified, không phụ thuộc vào việc name là null hay chuỗi rỗng.

## 5. Elvis giữ lại các giá trị hợp lệ như false và 0

Hãy xem cấu hình bật/tắt một tính năng. Nếu giá trị chưa được cấu hình, mặc định tính năng sẽ bật:

    #featureEnabled ?: true

Kết quả:

- Nếu featureEnabled là null, kết quả là true.
- Nếu featureEnabled là true, kết quả là true.
- Nếu featureEnabled là false, kết quả vẫn là false.

Điều này rất quan trọng. false là một giá trị Boolean đã được xác định, không phải dữ liệu bị thiếu. Nếu dùng điều kiện theo kiểu kiểm tra Boolean trực tiếp, ta có thể vô tình ghi đè lựa chọn tắt tính năng của người vận hành.

Tương tự với số:

    #retryLimit ?: 3

Nếu retryLimit bằng 0, kết quả vẫn là 0. Điều này phù hợp khi 0 mang ý nghĩa “không thử lại”. Elvis chỉ lấy 3 khi giá trị là null; số 0 không bị xem là rỗng.

Nếu yêu cầu nghiệp vụ là dùng mặc định cả khi số lần thử bằng 0, hãy diễn đạt rõ bằng điều kiện ba ngôi:

    #retryLimit != null and #retryLimit > 0
        ? #retryLimit
        : 3

Lúc này, điều kiện chủ động xác định rằng chỉ số dương mới được chấp nhận.

## 6. Dùng Elvis với truy cập thuộc tính có thể null

Elvis chỉ xử lý giá trị mà biểu thức bên trái trả về. Nếu việc tính biểu thức bên trái đã gây lỗi do truy cập một đối tượng null, Elvis không thể tự sửa lỗi đó.

Ví dụ, biểu thức sau có thể lỗi nếu customer là null:

    #customer.displayName ?: 'Guest'

Có thể kết hợp toán tử null-safe navigation với Elvis:

    #customer?.displayName ?: 'Guest'

Toán tử ?. truy cập displayName một cách an toàn: nếu customer là null, kết quả của phần truy cập là null. Elvis sau đó dùng Guest làm giá trị mặc định.

Cần phân biệt vai trò:

- ?. xử lý việc truy cập một thuộc tính khi đối tượng đứng trước có thể null.
- ?: xử lý giá trị null hoặc chuỗi rỗng sau khi biểu thức bên trái được đánh giá.

Hai toán tử có thể kết hợp, nhưng không thay thế nhau. Nếu chỉ dùng Elvis sau một phép truy cập có thể gây NullPointerException, giá trị mặc định có thể không bao giờ được đánh giá.

## 7. Điều kiện ba ngôi có thể xử lý nhiều trường hợp hơn

Điều kiện ba ngôi cho phép biểu đạt các chính sách cụ thể. Ví dụ chọn mức phí theo loại khách hàng:

    #customer.tier == 'GOLD'
        ? #baseFee * 0.8
        : #baseFee

Hoặc chọn nhãn dựa trên nhiều trạng thái:

    #order.cancelled
        ? 'CANCELLED'
        : (#order.paid ? 'PAID' : 'PENDING')

Ví dụ thứ hai có một toán tử ba ngôi lồng bên trong nhánh false. Ngoặc tròn làm rõ thứ tự và phạm vi của biểu thức con. Tuy nhiên, nếu số nhánh tăng lên nhiều, biểu thức sẽ khó đọc. Khi đó, nên đưa logic phân loại vào một phương thức Java hoặc một thành phần xử lý riêng.

Elvis cũng có thể được dùng bên trong một nhánh của toán tử ba ngôi:

    #user.active
        ? (#user.displayName ?: 'Unnamed user')
        : 'Inactive user'

Ở đây, điều kiện active quyết định nhánh. Trong nhánh true, Elvis chỉ cung cấp tên mặc định nếu displayName bị null hoặc là chuỗi rỗng.

## 8. Bảng lựa chọn toán tử

| Nhu cầu | Nên dùng | Lý do |
|---|---|---|
| Dùng giá trị thay thế khi kết quả là null | Elvis | Cú pháp ngắn, đúng mục đích mặc định |
| Dùng giá trị thay thế khi chuỗi là null hoặc rỗng | Elvis | Có xử lý đặc biệt cho chuỗi rỗng |
| Kiểm tra ngưỡng hoặc điều kiện nghiệp vụ | Ba ngôi đầy đủ | Điều kiện Boolean được viết rõ |
| Chọn nhánh theo trạng thái true/false | Ba ngôi đầy đủ | Có hai nhánh kết quả độc lập |
| Chấp nhận false hoặc 0 như giá trị đã cấu hình | Elvis | false và 0 được giữ nguyên |
| Coi 0 hoặc false là trường hợp cần mặc định | Ba ngôi đầy đủ | Có thể viết tiêu chí thay thế tường minh |
| Kiểm tra chuỗi chỉ có khoảng trắng | Ba ngôi đầy đủ hoặc chuẩn hóa trước | Elvis không tự trim chuỗi |

Một quy tắc thực tế là: khi ý định chỉ là “nếu thiếu thì dùng mặc định”, hãy chọn Elvis. Khi ý định là “nếu điều kiện này đúng thì chọn A, nếu không chọn B”, hãy chọn điều kiện ba ngôi đầy đủ.

## 9. Ví dụ đánh giá hai toán tử bằng Java

Có thể phân tích cả hai biểu thức bằng cùng một ExpressionParser. Mỗi biểu thức nhận biến từ EvaluationContext:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("name", "");
    context.setVariable("score", 72);

    Expression defaultName =
            parser.parseExpression("#name ?: 'Guest'");

    Expression resultLabel =
            parser.parseExpression(
                    "#score >= 50 ? 'PASS' : 'RETRY'");

    String name = defaultName.getValue(context, String.class);
    String result = resultLabel.getValue(context, String.class);

Với dữ liệu trên, name là Guest vì biến name là chuỗi rỗng. result là PASS vì score lớn hơn hoặc bằng 50.

Parser tạo Expression từ chuỗi. Khi getValue được gọi, SpEL đọc biến trong context, đánh giá toán tử và trả về giá trị của biểu thức. Việc chọn kiểu kết quả trong getValue giúp ứng dụng nhận được kiểu mong đợi; nếu biểu thức có thể trả về null hoặc dữ liệu không tương thích, ứng dụng cần xác định cách xử lý rõ ràng.

Trong ứng dụng thực tế, hãy dùng context phù hợp với các thao tác biểu thức cần thực hiện. Nếu rule chỉ cần đọc dữ liệu đơn giản, có thể chọn context giới hạn quyền. Không đưa các biểu thức không đáng tin cậy vào một context có quyền gọi bean hoặc phương thức rộng.

## 10. Kiểm thử các trường hợp biên

Khi xây dựng rule có Elvis hoặc ternary, nên kiểm thử những giá trị dễ bị nhầm:

- null: xác nhận giá trị mặc định được dùng.
- Chuỗi rỗng: xác nhận Elvis dùng mặc định.
- Chuỗi chỉ chứa khoảng trắng: xác nhận chuỗi được giữ nguyên nếu chưa có quy tắc trim.
- false: xác nhận Elvis giữ false.
- 0: xác nhận Elvis giữ số 0.
- Điều kiện true và false: xác nhận mỗi nhánh của ternary trả về đúng kết quả.
- Đối tượng gốc null: xác nhận null-safe navigation được dùng ở đúng vị trí nếu cần.

Không nên chỉ kiểm thử một trường hợp bình thường. Nhiều lỗi cấu hình xuất hiện ở dữ liệu biên, đặc biệt khi giá trị false hoặc 0 là lựa chọn hợp lệ của người dùng.

## Kết luận

Elvis và điều kiện ba ngôi đầy đủ đều giúp chọn giá trị trong SpEL, nhưng khác nhau ở tiêu chí lựa chọn. Elvis trả về giá trị bên trái nếu nó khác null và khác chuỗi rỗng; nếu không, nó trả về giá trị mặc định bên phải. Điều kiện ba ngôi đánh giá một điều kiện Boolean rồi chọn một trong hai nhánh kết quả.

Elvis là lựa chọn ngắn gọn cho giá trị mặc định. Toán tử ba ngôi đầy đủ phù hợp với quyết định nghiệp vụ có điều kiện rõ ràng. Hãy nhớ rằng false, 0, collection rỗng và chuỗi chỉ có dấu cách vẫn là giá trị được giữ lại bởi Elvis; nếu muốn xử lý chúng như trường hợp đặc biệt, hãy viết điều kiện cụ thể.