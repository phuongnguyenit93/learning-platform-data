Bạn giải thích vì sao String được thiết kế bất biến trong Java và lợi ích của tính chất này đối với việc chia sẻ dữ liệu như thế nào?
Bạn phân biệt giá trị chuỗi với tham chiếu đến đối tượng String khi thực hiện phép gán trong Java ra sao?
Bạn phân tích điều gì xảy ra khi gọi concat trên một String nhưng bỏ qua giá trị trả về như thế nào?
Bạn so sánh hành vi của String với một đối tượng có thể thay đổi trạng thái khi được truyền vào phương thức như thế nào?
Bạn giải thích cách String bất biến giúp giảm rủi ro tranh chấp dữ liệu khi nhiều thread cùng sử dụng một giá trị ra sao?
Bạn đánh giá những trường hợp dùng String để lưu bí mật như mật khẩu hoặc token có bất lợi gì về vòng đời dữ liệu trong bộ nhớ?
Bạn thiết kế một API nhận chuỗi đầu vào sao cho tránh thay đổi ngoài ý muốn và biểu diễn rõ ý nghĩa nghiệp vụ như thế nào?
Bạn phân biệt việc tạo String từ literal và tạo bằng constructor nhận một String khác về tham chiếu và nội dung ra sao?
Bạn giải thích khái niệm string pool và mục tiêu tái sử dụng các literal trùng nội dung trong Java như thế nào?
Bạn phân tích sự khác nhau giữa phép so sánh == và equals khi hai biến cùng chứa chuỗi có nội dung giống nhau ra sao?
Bạn giải thích tại sao hai string literal giống nhau thường chia sẻ một tham chiếu nhưng không nên dựa vào điều đó để so sánh nội dung như thế nào?
Bạn dùng equals để so sánh chuỗi an toàn khi một trong hai tham chiếu có thể là null như thế nào?
Bạn lựa chọn Objects.equals hoặc gọi equals trên hằng chuỗi khi cần so sánh giá trị đầu vào có thể null theo tiêu chí nào?
Bạn phân biệt equalsIgnoreCase với equals khi hợp đồng dữ liệu yêu cầu phân biệt chữ hoa và chữ thường như thế nào?
Bạn xác định hạn chế của equalsIgnoreCase khi so sánh văn bản đa ngôn ngữ có quy tắc phân biệt chữ riêng ra sao?
Bạn giải thích tác động của String.intern đối với string pool và các trường hợp cần cân nhắc trước khi sử dụng như thế nào?
Bạn phân tích vì sao intern hàng triệu chuỗi người dùng khác nhau có thể gây áp lực bộ nhớ thay vì tiết kiệm như mong đợi ra sao?
Bạn kiểm chứng việc compiler gộp các hằng chuỗi và nối chuỗi tại compile time khác với nối giá trị runtime như thế nào?
Bạn phân biệt tham chiếu String được chia sẻ qua string pool với việc các chuỗi có chung nội dung ký tự luôn có chung object ra sao?
Bạn phân biệt những đặc tính String được API bảo đảm với các chi tiết triển khai có thể thay đổi giữa các phiên bản JDK như thế nào?
Bạn giải thích cách String.length đo độ dài chuỗi và lý do nó không nhất thiết bằng số ký tự người dùng nhìn thấy ra sao?
Bạn phân biệt char, UTF-16 code unit, Unicode code point và grapheme cluster qua một chuỗi có emoji như thế nào?
Bạn xác định vì sao một ký tự Unicode ngoài Basic Multilingual Plane thường cần surrogate pair trong String Java như thế nào?
Bạn phân tích rủi ro khi dùng charAt để lấy một ký tự được hiển thị thành emoji hoặc biểu tượng phức hợp ra sao?
Bạn dùng codePointAt và codePointCount để khảo sát nội dung Unicode mà không nhầm với số UTF-16 code unit như thế nào?
Bạn sử dụng offsetByCodePoints khi cần dịch chuyển chỉ số theo code point thay vì theo char ra sao?
Bạn thiết kế vòng lặp duyệt chuỗi theo code point và chuyển kết quả về chuỗi mới như thế nào?
Bạn giải thích vì sao code point vẫn không đủ để đếm số ký tự hiển thị trong văn bản có dấu kết hợp hoặc emoji nối chuỗi ra sao?
Bạn lựa chọn công cụ phân đoạn grapheme phù hợp khi chức năng yêu cầu xóa đúng một ký tự mà người dùng nhìn thấy như thế nào?
Bạn phân tích một chuỗi emoji gia đình có nhiều code point và ký tự nối nhưng hiển thị như một biểu tượng ra sao?
Bạn kiểm tra nguy cơ substring cắt vào giữa surrogate pair khi giới hạn độ dài văn bản theo chỉ số String như thế nào?
Bạn thiết kế tính năng giới hạn tên người dùng theo số ký tự hiển thị mà không làm hỏng dữ liệu Unicode ra sao?
Bạn phân biệt so sánh chuỗi theo mã UTF-16 với việc sắp xếp theo ngôn ngữ tự nhiên của người dùng như thế nào?
Bạn giải thích vì sao String.compareTo không tự động phản ánh thứ tự từ điển của tiếng Việt hoặc ngôn ngữ khác ra sao?
Bạn sử dụng Collator và Locale khi ứng dụng cần sắp xếp tên người dùng theo quy tắc ngôn ngữ như thế nào?
Bạn đánh giá cách xử lý chữ có dấu và không dấu khi triển khai tìm kiếm không phân biệt dấu theo yêu cầu nghiệp vụ ra sao?
Bạn giải thích ý nghĩa của Unicode normalization và sự khác nhau giữa hai chuỗi nhìn giống nhau nhưng có cách mã hóa khác nhau như thế nào?
Bạn phân biệt dạng chuẩn NFC và NFD khi cần chuẩn hóa dữ liệu văn bản từ nhiều hệ thống ra sao?
Bạn thiết kế quy trình chuẩn hóa Unicode trước khi lưu hoặc so sánh chuỗi mà không vô tình thay đổi dữ liệu có ý nghĩa như thế nào?
Bạn phân tích rủi ro khi xóa toàn bộ dấu kết hợp khỏi chuỗi để tìm kiếm hoặc tạo định danh duy nhất ra sao?
Bạn giải thích tại sao chuyển chữ hoa và chữ thường có thể phụ thuộc Locale đối với một số ngôn ngữ như thế nào?
Bạn lựa chọn Locale.ROOT hay Locale người dùng khi chuẩn hóa mã kỹ thuật so với hiển thị tên riêng ra sao?
Bạn thiết kế kiểm thử cho chuyển chữ hoa và chữ thường khi dữ liệu chứa chữ I và các trường hợp đặc thù của tiếng Thổ Nhĩ Kỳ như thế nào?
Bạn phân biệt case folding phục vụ so khớp văn bản với toLowerCase thông thường và những giới hạn cần lưu ý ra sao?
Bạn đánh giá nguy cơ dùng phép chuyển chữ thường làm khóa đăng nhập mà không có quy tắc chuẩn hóa định danh nhất quán như thế nào?
Bạn mô tả cách isEmpty và isBlank khác nhau khi kiểm tra chuỗi rỗng hoặc chỉ gồm khoảng trắng như thế nào?
Bạn phân biệt trim với strip trong cách xử lý ký tự khoảng trắng và phạm vi hỗ trợ Unicode ra sao?
Bạn kiểm tra và xử lý các loại khoảng trắng Unicode như non-breaking space mà trim hoặc strip có thể không loại bỏ theo mong đợi như thế nào?
Bạn thiết kế quy tắc loại bỏ khoảng trắng ở đầu cuối tên người dùng mà vẫn giữ nguyên khoảng trắng có ý nghĩa bên trong như thế nào?
Bạn phân biệt stripLeading, stripTrailing và strip khi chỉ một phía của chuỗi cần được chuẩn hóa ra sao?
Bạn đánh giá có nên tự động loại bỏ ký tự điều khiển hoặc ký tự vô hình trong dữ liệu người dùng theo những tiêu chí nào?
Bạn lựa chọn phương thức startsWith, endsWith hoặc contains khi kiểm tra một dấu hiệu trong chuỗi thay vì dùng regex ra sao?
Bạn phân biệt indexOf với lastIndexOf khi xác định vị trí dấu phân cách xuất hiện nhiều lần như thế nào?
Bạn xác định cách xử lý kết quả -1 của indexOf để tránh truy cập substring bằng chỉ số không hợp lệ ra sao?
Bạn thiết kế phương thức lấy phần mở rộng file từ tên file có nhiều dấu chấm hoặc không có dấu chấm như thế nào?
Bạn giải thích quy tắc chỉ số bắt đầu và kết thúc của substring và cách tránh lỗi off-by-one ra sao?
Bạn xử lý trường hợp beginIndex bằng endIndex khi gọi substring và xác định kết quả theo hợp đồng API như thế nào?
Bạn phân tích vì sao substring không thể thay thế thao tác phân đoạn Unicode theo grapheme khi cắt văn bản như thế nào?
Bạn sử dụng regionMatches để so sánh một phần chuỗi mà không phải tạo thêm nhiều substring trong trường hợp nào?
Bạn phân biệt String.replace với String.replaceAll về việc đối số được hiểu là chuỗi literal hay regex như thế nào?
Bạn giải thích vì sao replaceFirst chỉ thay lần khớp đầu tiên và cách kiểm chứng đúng phạm vi thay thế ra sao?
Bạn thiết kế chức năng thay thế ký tự đặc biệt trong nội dung người dùng mà không để regex hiểu nhầm dữ liệu là pattern như thế nào?
Bạn phân biệt việc chèn ký tự xuống dòng theo escape sequence với việc văn bản có nhiều dòng được đọc từ file ra sao?
Bạn sử dụng String.lines để duyệt các dòng văn bản và đánh giá cách API xử lý các dấu kết thúc dòng như thế nào?
Bạn lựa chọn text block thay cho chuỗi nối nhiều dòng khi lưu mẫu JSON hoặc SQL trong mã nguồn Java ra sao?
Bạn phân tích ảnh hưởng của indentation và line terminator khi sử dụng Java text block trong một chuỗi dự kiến so khớp chính xác như thế nào?
Bạn sử dụng stripIndent và translateEscapes khi cần xử lý nội dung nhiều dòng với quy tắc rõ ràng ra sao?
Bạn đánh giá cách dùng String.repeat để tạo chuỗi lặp và rủi ro về bộ nhớ nếu số lần lặp quá lớn như thế nào?
Bạn giải thích vì sao cộng String trong vòng lặp có thể tạo nhiều giá trị trung gian và ảnh hưởng đến cấp phát bộ nhớ ra sao?
Bạn lựa chọn StringBuilder thay cho phép nối chuỗi liên tục trong trường hợp nào dựa trên đặc điểm workload?
Bạn phân biệt StringBuilder và StringBuffer theo bảo đảm đồng bộ và chi phí truy cập trong nhiều thread như thế nào?
Bạn thiết kế hàm ghép nhiều phần tử bằng StringBuilder có xử lý phân cách và collection rỗng như thế nào?
Bạn sử dụng StringJoiner hoặc String.join thay cho việc tự quản lý dấu phân cách trong những tình huống nào?
Bạn so sánh StringBuilder.append với String.format khi ưu tiên hiệu năng hoặc tính dễ đọc của mã như thế nào?
Bạn giải thích vì sao chỉ gọi toString sau khi hoàn thành StringBuilder giúp tránh tạo bản kết quả trung gian không cần thiết ra sao?
Bạn phân tích những trường hợp compiler hoặc runtime có thể tối ưu phép nối String bằng toán tử cộng thay vì tạo mã chậm như thế nào?
Bạn phân biệt tối ưu nối chuỗi của JDK hiện đại với giả định mọi phép cộng String đều tạo StringBuilder tường minh như thế nào?
Bạn thiết kế benchmark JMH so sánh các cách ghép chuỗi mà tránh constant folding và dead-code elimination ra sao?
Bạn đánh giá tác động của việc đo chuỗi ngắn và chuỗi rất dài đến lựa chọn kỹ thuật nối chuỗi như thế nào?
Bạn kiểm tra nguyên nhân tăng allocation rate khi một API liên tục tạo chuỗi tạm từ các trường dữ liệu như thế nào?
Bạn giải thích vì sao String bất biến không có nghĩa là mọi thao tác xử lý chuỗi đều không tạo thêm đối tượng như thế nào?
Bạn xác định cách phân tích hiệu năng của một phương thức dùng nhiều substring, replace và format từ dữ liệu JFR như thế nào?
Bạn đánh giá lợi ích và rủi ro khi cache chuỗi được dựng từ dữ liệu có số lượng khóa gần như không giới hạn ra sao?
Bạn phân tích vì sao không nên mặc định String.equals là phép so sánh constant-time khi kiểm tra dữ liệu nhạy cảm như thế nào?
Bạn lựa chọn cách so sánh bí mật tránh lộ thông tin theo thời gian thay vì dùng equals thông thường trong trường hợp nào?
Bạn giải thích vai trò của Charset trong quá trình chuyển đổi giữa String và mảng byte như thế nào?
Bạn phân biệt Unicode code point với byte được tạo ra bởi một encoding như UTF-8 trong một ví dụ có tiếng Việt ra sao?
Bạn dùng StandardCharsets.UTF_8 để mã hóa và giải mã String mà không phụ thuộc charset mặc định của môi trường như thế nào?
Bạn phân tích hiện tượng mojibake khi byte UTF-8 bị giải mã bằng charset không tương ứng và cách khôi phục dữ liệu ra sao?
Bạn đánh giá việc gọi getBytes mà không chỉ định charset có thể khiến hệ thống hoạt động khác nhau giữa các JDK hoặc máy chủ như thế nào?
Bạn giải thích cách một ký tự có dấu hoặc emoji được biểu diễn bằng nhiều byte UTF-8 nhưng có số code unit UTF-16 khác nhau ra sao?
Bạn thiết kế giao thức truyền chuỗi qua socket có khai báo charset và cách xác định độ dài payload theo byte như thế nào?
Bạn phân biệt giới hạn kích thước văn bản theo byte UTF-8 và giới hạn theo String.length trong một API upload ra sao?
Bạn giải thích vai trò của CharsetEncoder và CharsetDecoder khi muốn kiểm soát hành vi với dữ liệu không hợp lệ như thế nào?
Bạn xử lý byte sequence UTF-8 không hợp lệ theo chính sách báo lỗi hoặc thay thế ký tự bằng cách nào?
Bạn đánh giá rủi ro mất dữ liệu khi mã hóa chuỗi chứa ký tự không biểu diễn được trong một charset cũ như thế nào?
Bạn xác định cách phát hiện và xử lý unpaired surrogate trong String trước khi mã hóa sang UTF-8 ra sao?
Bạn phân biệt byte order mark với nội dung văn bản khi đọc file UTF-8 đến từ nhiều công cụ như thế nào?
Bạn thiết kế cách đọc một file UTF-8 có hoặc không có BOM mà không làm hỏng ký tự đầu tiên ra sao?
Bạn sử dụng Files.readString và Files.writeString với charset tường minh để bảo đảm tính nhất quán ra sao?
Bạn lựa chọn BufferedReader hoặc streaming decoder để xử lý file văn bản lớn thay vì tải toàn bộ vào String như thế nào?
Bạn đánh giá cách xử lý một chuỗi bị cắt giữa multibyte sequence khi đọc dữ liệu UTF-8 theo từng chunk ra sao?
Bạn thiết kế test round-trip từ String sang byte và quay về String để kiểm tra độ toàn vẹn dữ liệu đa ngôn ngữ như thế nào?
Bạn phân tích giới hạn của round-trip qua encoding không hỗ trợ đầy đủ Unicode dù dữ liệu gốc vẫn là String như thế nào?
Bạn giải thích vai trò của java.util.regex.Pattern và Matcher trong việc biên dịch và áp dụng biểu thức chính quy như thế nào?
Bạn phân biệt String.matches với Matcher.find khi cần kiểm tra toàn bộ chuỗi so với tìm một đoạn khớp như thế nào?
Bạn giải thích sự khác nhau giữa Matcher.matches, lookingAt và find đối với vị trí bắt đầu và phạm vi khớp ra sao?
Bạn lựa chọn Pattern.compile dùng lại khi một regex được áp dụng cho lượng lớn đầu vào như thế nào?
Bạn phân tích tính an toàn khi chia sẻ Pattern giữa các thread và lý do không nên chia sẻ cùng một Matcher mutable ra sao?
Bạn giải thích vì sao dấu chấm trong regex có ý nghĩa đặc biệt và cách tách chuỗi theo dấu chấm literal như thế nào?
Bạn phân biệt escape ký tự trong Java string literal với escape ký tự của chính biểu thức regex khi viết Pattern như thế nào?
Bạn sử dụng Pattern.quote để tìm chính xác một từ khóa do người dùng nhập mà không bị diễn giải thành regex ra sao?
Bạn giải thích vai trò của Matcher.quoteReplacement khi văn bản thay thế có dấu đô la hoặc dấu gạch chéo ngược như thế nào?
Bạn phân tích sự khác biệt giữa greedy quantifier và reluctant quantifier khi trích xuất một đoạn văn bản có nhiều dấu phân cách ra sao?
Bạn sử dụng capturing group và named group để trích xuất các thành phần của một mã định danh có cấu trúc như thế nào?
Bạn phân biệt non-capturing group với capturing group khi chỉ cần gom phạm vi của một nhánh regex ra sao?
Bạn giải thích vai trò của anchors và word boundaries khi muốn tìm từ độc lập thay vì một đoạn nằm trong từ dài như thế nào?
Bạn đánh giá các giới hạn của ký hiệu word boundary mặc định với ngôn ngữ có dấu và nhiều hệ chữ như thế nào?
Bạn phân biệt Pattern.CASE_INSENSITIVE và UNICODE_CASE khi thực hiện so khớp không phân biệt chữ hoa trên dữ liệu quốc tế ra sao?
Bạn giải thích ý nghĩa của các cờ MULTILINE và DOTALL trong regex xử lý văn bản nhiều dòng như thế nào?
Bạn lựa chọn lookahead hoặc lookbehind trong một tình huống kiểm tra ngữ cảnh mà không lấy phần ngữ cảnh vào kết quả khớp ra sao?
Bạn phân tích những giới hạn và nguy cơ khó đọc của một regex sử dụng nhiều lookaround lồng nhau ra sao?
Bạn đánh giá tác động của nested quantifier đến catastrophic backtracking trên chuỗi đầu vào có chủ ý gây quá tải như thế nào?
Bạn thiết kế cách bảo vệ hệ thống khỏi regex denial of service khi pattern hoặc input đến từ nguồn không tin cậy ra sao?
Bạn lựa chọn kiểm tra chuỗi bằng startsWith, indexOf hoặc thuật toán tường minh thay cho regex khi yêu cầu đơn giản như thế nào?
Bạn dùng Matcher.region để chỉ tìm trong một phần văn bản mà không cần tạo substring mới ra sao?
Bạn phân biệt replaceAll với Matcher.appendReplacement và appendTail khi cần thay thế theo ngữ cảnh của từng lần khớp như thế nào?
Bạn xử lý giá trị group có thể null khi một nhánh regex tùy chọn không tham gia lần khớp như thế nào?
Bạn phân tích vì sao String.split mặc định có thể bỏ các trường rỗng ở cuối dữ liệu và ảnh hưởng đến việc đọc file phân cách ra sao?
Bạn lựa chọn tham số limit của split khi muốn giữ tất cả cột trống, kể cả cột cuối, như thế nào?
Bạn giải thích vì sao split theo dấu phẩy không đủ để parse CSV có dấu phẩy hoặc dấu xuống dòng nằm trong trường được trích dẫn ra sao?
Bạn thiết kế cách validate dữ liệu đầu vào bằng regex mà không để pattern trở thành nơi chứa mọi quy tắc nghiệp vụ khó kiểm thử như thế nào?
Bạn kiểm thử một regex bằng các ca input rỗng, Unicode, trường hợp biên và chuỗi bất thường có độ dài lớn ra sao?
Bạn giải thích những rủi ro khi dùng String như một cấu trúc SQL động có nối trực tiếp dữ liệu người dùng như thế nào?
Bạn thiết kế API tạo truy vấn database bằng tham số ràng buộc thay vì nối chuỗi dữ liệu đầu vào ra sao?
Bạn phân biệt encode cho URL, HTML và JSON theo ngữ cảnh để tránh áp dụng sai cơ chế escaping như thế nào?
Bạn phân tích rủi ro khi chỉ xóa ký tự đặc biệt khỏi chuỗi thay cho việc kiểm tra và encode theo ngữ cảnh xuất dữ liệu ra sao?
Bạn kiểm soát dữ liệu đầu vào dùng làm tên file để tránh path traversal dù ứng dụng đã chuẩn hóa một số ký tự như thế nào?
Bạn thiết kế quy trình log chuỗi lỗi sao cho tránh lộ mật khẩu, token hoặc dữ liệu cá nhân mà vẫn hỗ trợ chẩn đoán ra sao?
Bạn giải thích nguy cơ log forging khi một giá trị String do người dùng nhập chứa dấu xuống dòng hoặc ký tự điều khiển như thế nào?
Bạn phân biệt việc biểu diễn null, chuỗi rỗng và chuỗi chỉ chứa whitespace trong hợp đồng API theo ý nghĩa nghiệp vụ ra sao?
Bạn lựa chọn Optional<String> hoặc một quy ước xác thực khác khi phương thức có thể không tìm thấy giá trị chuỗi như thế nào?
Bạn thiết kế chuẩn hóa đầu vào trước khi tra cứu cache mà không tạo xung đột giữa hai chuỗi thực sự khác nhau ra sao?
Bạn phân tích vì sao dùng String làm key trong HashMap cần hiểu equals và hashCode chứ không chỉ dựa vào tham chiếu như thế nào?
Bạn phân tích rủi ro khi công khai StringBuilder mutable qua API thay vì trả về giá trị String bất biến như thế nào?
Bạn thiết kế API trả về một chuỗi được tạo từ dữ liệu mutable mà bảo đảm kết quả không đổi sau khi phương thức trả về như thế nào?
Bạn so sánh phép chuyển đổi String.valueOf với gọi toString trên một đối tượng có thể null theo hành vi đầu ra ra sao?
Bạn phân biệt String.valueOf trên mảng ký tự với hành vi mặc định khi chuyển một mảng khác loại sang chuỗi như thế nào?
Bạn phân tích vai trò của String.format và Locale khi định dạng số thập phân hoặc tiền tệ cho người dùng ở nhiều nước như thế nào?
Bạn thiết kế cách tách phần định dạng dành cho người dùng khỏi định dạng máy đọc để tránh ảnh hưởng của Locale mặc định như thế nào?
Bạn lựa chọn MessageFormat hay String.format khi mẫu thông báo cần tái sử dụng và bản địa hóa như thế nào?
Bạn đánh giá các giới hạn của việc cắt chuỗi theo số ký tự cố định khi UI có font và độ rộng hiển thị khác nhau ra sao?
Bạn phân tích vì sao hai chuỗi nhìn như nhau nhưng equals trả về false khi dữ liệu chứa ký tự kết hợp hoặc ký tự vô hình ra sao?
Bạn sử dụng phương pháp quan sát code point và byte UTF-8 để tìm nguyên nhân sai khác chuỗi mà mắt thường không nhận ra như thế nào?
Bạn xác định cách đo thời gian và memory allocation khi một pipeline xử lý hàng triệu dòng văn bản mà không tạo dữ liệu benchmark sai lệch ra sao?
Bạn thiết kế cơ chế xử lý text theo luồng để tránh OutOfMemoryError khi một file đầu vào quá lớn như thế nào?
Bạn đánh giá chi phí regex compilation và matcher allocation khi một service cần kiểm tra nhiều chuỗi ngắn dưới tải cao ra sao?
Bạn kiểm tra liệu tối ưu nối chuỗi bằng StringBuilder có thực sự cải thiện p95 latency của một endpoint so với bottleneck I/O như thế nào?
Một chương trình so sánh hai String cùng nội dung bằng == và chạy đúng trong test nhưng sai ở production, bạn sẽ điều tra string pool ra sao?
Một ứng dụng báo giới hạn tên dài 20 ký tự nhưng từ chối chuỗi chứa nhiều emoji ngắn, bạn sẽ kiểm tra UTF-16 và quy tắc đếm ký tự như thế nào?
Một file tiếng Việt bị hiển thị thành ký tự lỗi sau khi đổi máy chủ, bạn sẽ truy vết charset ở các bước đọc, truyền và ghi dữ liệu ra sao?
Một hệ thống tìm kiếm không nhận ra hai tên có dấu nhìn giống hệt nhau, bạn sẽ kiểm tra Unicode normalization và quy tắc so khớp như thế nào?
Một chức năng split dữ liệu bằng dấu phân cách làm mất cột trống cuối cùng, bạn sẽ phân tích tham số limit và kiểm thử dữ liệu đầu vào ra sao?
Một regex kiểm tra email đơn giản khiến CPU tăng vọt với chuỗi rất dài, bạn sẽ phát hiện catastrophic backtracking và thiết kế giải pháp ra sao?
Một chức năng thay thế văn bản lỗi khi chuỗi thay thế chứa ký tự đô la, bạn sẽ kiểm tra cách Matcher diễn giải replacement như thế nào?
Một service ghép chuỗi trong vòng lặp lớn làm allocation rate tăng, bạn sẽ xác định điểm nóng và đánh giá các lựa chọn tối ưu như thế nào?
Một API dùng toLowerCase không chỉ định Locale làm biến đổi sai mã định danh ở một số máy, bạn sẽ sửa chính sách chuẩn hóa như thế nào?
Một hệ thống đọc dữ liệu phân mảnh làm hỏng emoji ở biên buffer, bạn sẽ thiết kế decoder duy trì trạng thái giữa các chunk ra sao?
Một nhóm muốn dùng equalsIgnoreCase để đối chiếu tên người dùng đa ngôn ngữ, bạn sẽ phân tích giới hạn và xây dựng quy tắc phù hợp như thế nào?
Bạn xây dựng tiêu chí review mã xử lý String về tính bất biến, Unicode, regex, charset, hiệu năng và an toàn dữ liệu như thế nào?
