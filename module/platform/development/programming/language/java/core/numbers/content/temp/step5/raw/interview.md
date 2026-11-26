Bạn phân biệt các kiểu số nguyên `byte`, `short`, `int`, `long` và miền giá trị của chúng trong Java như thế nào?
Bạn giải thích vì sao `char` là kiểu nguyên không dấu nhưng không thể thay thế trực tiếp cho mọi thao tác xử lý ký tự Unicode ra sao?
Bạn xác định một số nguyên cần kiểu `int`, `long` hay `BigInteger` dựa trên miền dữ liệu và phép toán dự kiến như thế nào?
Bạn giải thích cách Java biểu diễn số nguyên âm bằng bù hai và ảnh hưởng của biểu diễn này lên các phép toán bit ra sao?
Bạn kiểm chứng giá trị `Integer.MIN_VALUE` và `Integer.MAX_VALUE` bằng cách liên hệ số bit và bit dấu như thế nào?
Bạn phân biệt literal số nguyên thập phân, nhị phân, bát phân và thập lục phân trong Java và tránh nhầm lẫn khi đọc mã như thế nào?
Bạn sử dụng hậu tố `L` cho literal số nguyên và xác định lỗi có thể xảy ra khi một literal vượt phạm vi `int` ra sao?
Bạn giải thích giới hạn khi sử dụng dấu gạch dưới trong literal số và lợi ích của nó đối với khả năng đọc mã như thế nào?
Bạn phân tích lý do phép cộng hai giá trị `byte` có kết quả kiểu `int` và cách gán trở lại biến `byte` như thế nào?
Bạn diễn giải quy tắc binary numeric promotion trong biểu thức có `int`, `long`, `float` và `double` như thế nào?
Bạn giải thích khác biệt giữa phép chia số nguyên và phép chia số thực khi các toán hạng có kiểu khác nhau ra sao?
Bạn xác định quy tắc làm tròn về không của phép chia số nguyên có số âm và tác động đến thuật toán chia nhóm như thế nào?
Bạn phân biệt phép chia lấy dư `%` của Java với phép modulo toán học đối với số âm bằng cách nào?
Bạn sử dụng `Math.floorDiv` và `Math.floorMod` khi cần chia hoặc lấy phần dư theo quy tắc làm tròn xuống như thế nào?
Bạn phân tích hiện tượng tràn số trong phép cộng, trừ và nhân kiểu `int` hoặc `long` khi không có ngoại lệ tự động như thế nào?
Bạn xác định nguyên nhân một bộ đếm kiểu `int` chuyển thành số âm sau khi tăng liên tục và lựa chọn cách khắc phục ra sao?
Bạn dùng `Math.addExact`, `subtractExact`, `multiplyExact` và `toIntExact` để phát hiện tràn số trong những trường hợp nào?
Bạn giải thích vì sao `Math.abs(Integer.MIN_VALUE)` không cho giá trị dương tương ứng và đề xuất cách xử lý an toàn như thế nào?
Bạn kiểm tra trường hợp chia `Integer.MIN_VALUE` cho `-1` và phân biệt hành vi với phép chia cho không như thế nào?
Bạn thiết kế phép cộng nhiều số nguyên sao cho không tràn trong kết quả trung gian dù kết quả cuối có thể nằm trong miền giá trị như thế nào?
Bạn phân biệt overflow và underflow trong tính toán số nguyên so với các khái niệm này trong tính toán dấu phẩy động ra sao?
Bạn xác định khi nào nên dùng `long` làm bộ đếm hoặc giá trị thời gian thay vì `int` trong một ứng dụng chạy dài ngày như thế nào?
Bạn thiết kế phép nhân kích thước hoặc tính dung lượng bộ đệm từ dữ liệu người dùng để tránh tràn số trước khi cấp phát như thế nào?
Bạn xử lý sự khác nhau giữa phép so sánh signed và unsigned đối với dữ liệu nhị phân đọc từ giao thức ngoài Java như thế nào?
Bạn sử dụng `Integer.toUnsignedLong`, `compareUnsigned` và `divideUnsigned` khi thao tác với trường số không dấu như thế nào?
Bạn giải thích vai trò của các toán tử `&`, `|`, `^` và `~` khi trích xuất hoặc cập nhật cờ bit trong số nguyên ra sao?
Bạn phân biệt `>>` và `>>>` khi dịch phải số âm và phân tích tác động của việc mở rộng bit dấu như thế nào?
Bạn xác định vì sao số bit dịch thực tế bị giới hạn theo độ rộng của kiểu `int` hoặc `long` trong Java như thế nào?
Bạn dùng `Integer.bitCount`, `numberOfLeadingZeros` và `numberOfTrailingZeros` để tối ưu những thuật toán thao tác bit nào?
Bạn thiết kế đóng gói nhiều trường số nguyên vào một giá trị bitmask và kiểm tra tính đúng đắn của thao tác dịch bit ra sao?
Bạn lựa chọn `Integer.rotateLeft` và `rotateRight` thay cho phép dịch bit thông thường trong những thuật toán nào và vì sao?
Bạn phân biệt chuyển kiểu widening primitive conversion và narrowing primitive conversion về khả năng mất dữ liệu như thế nào?
Bạn giải thích vì sao chuyển `long` sang `float` có thể mất độ chính xác dù miền giá trị của `float` rất rộng như thế nào?
Bạn kiểm chứng kết quả khi ép một số nguyên lớn từ `long` sang `int` và xác định trường hợp cần kiểm tra giới hạn trước như thế nào?
Bạn xử lý chuyển đổi từ `double` sang `int` khi đầu vào là giá trị ngoài miền, `NaN` hoặc vô cực như thế nào?
Bạn phân tích quy tắc ép kiểu số thực sang số nguyên về phần thập phân và điều kiện cần làm tròn tường minh như thế nào?
Bạn phân biệt phép ép kiểu tường minh và chuyển đổi có kiểm tra bằng `Math.toIntExact` khi đọc dữ liệu từ API bên ngoài ra sao?
Bạn giải thích cách boxing và unboxing chuyển giữa kiểu nguyên thủy với các wrapper như `Integer` và `Long` như thế nào?
Bạn chẩn đoán `NullPointerException` khi unboxing một biến `Integer` có giá trị `null` trong biểu thức số học như thế nào?
Bạn phân biệt `==` và `equals` khi so sánh hai đối tượng `Integer` và ảnh hưởng của wrapper cache ra sao?
Bạn giải thích vì sao không nên dựa vào identity của các đối tượng wrapper số để quyết định hai giá trị bằng nhau như thế nào?
Bạn đánh giá chi phí boxing và unboxing khi xử lý hàng triệu số bằng collection hoặc stream như thế nào?
Bạn lựa chọn `IntStream`, `LongStream` hoặc `DoubleStream` để hạn chế boxing trong pipeline tính toán ra sao?
Bạn xác định khi nào kiểu wrapper là cần thiết trong generic API và cách xử lý giá trị thiếu một cách rõ ràng như thế nào?
Bạn sử dụng `Integer.parseInt`, `Long.parseLong` và các API tương ứng để phân tích chuỗi số, đồng thời xử lý dữ liệu không hợp lệ như thế nào?
Bạn phân biệt `parseInt` với `decode` khi đầu vào có tiền tố thể hiện cơ số và xác định rủi ro khi chấp nhận định dạng ngoài mong đợi ra sao?
Bạn thiết kế kiểm tra phạm vi cho số nhập từ chuỗi trước khi thực hiện phép tính có thể làm tràn như thế nào?
Bạn xử lý dữ liệu số có dấu phân cách theo vùng miền bằng `NumberFormat` nhưng vẫn phân biệt với chuỗi số trong giao thức máy tính ra sao?
Bạn kiểm tra chuỗi đầu vào có ký tự dư sau số được phân tích để tránh chấp nhận sai giá trị như thế nào?
Bạn phân biệt kiểu `float` và `double` về số bit, độ chính xác và miền số mũ trong mô hình IEEE 754 như thế nào?
Bạn giải thích vì sao giá trị thập phân như `0.1` thường không được biểu diễn chính xác bằng dấu phẩy động nhị phân như thế nào?
Bạn mô tả sự khác nhau giữa sai số biểu diễn và sai số tích lũy khi thực hiện nhiều phép toán dấu phẩy động ra sao?
Bạn xác định vì sao phép cộng dấu phẩy động có thể không kết hợp và thiết kế kiểm thử cho thuật toán cộng dồn như thế nào?
Bạn giải thích vai trò của mantissa, exponent và bit dấu khi mô tả giới hạn độ chính xác của `double` như thế nào?
Bạn phân biệt độ chính xác tương đối và độ chính xác tuyệt đối khi đánh giá kết quả phép tính dấu phẩy động ra sao?
Bạn sử dụng `Math.ulp` để ước lượng khoảng cách giữa các giá trị dấu phẩy động biểu diễn được gần một số như thế nào?
Bạn chọn epsilon tuyệt đối và tương đối khi so sánh hai kết quả dấu phẩy động theo yêu cầu bài toán ra sao?
Bạn xác định vì sao dùng trực tiếp `a == b` có thể không phù hợp cho kết quả tính toán số thực nhưng vẫn hữu ích ở tình huống nào?
Bạn thiết kế cách so sánh hai số thực khi một trong hai có thể là `NaN` hoặc vô cực như thế nào?
Bạn phân biệt hành vi của `Double.NaN == Double.NaN`, `Double.equals` và `Double.compare` theo hợp đồng của từng API như thế nào?
Bạn giải thích sự khác nhau giữa `+0.0` và `-0.0` trong phép so sánh, phép chia và sắp xếp số thực ra sao?
Bạn xác định cách `Double.isNaN` và `Double.isInfinite` giúp kiểm tra kết quả tính toán bất thường như thế nào?
Bạn phân tích vì sao phép chia số thực cho không không xử lý giống phép chia số nguyên cho không như thế nào?
Bạn lựa chọn cách xử lý `NaN` khi tính tổng, trung bình hoặc xếp hạng dữ liệu đo đạc để tránh lan truyền lỗi âm thầm ra sao?
Bạn giải thích ý nghĩa của normal và subnormal numbers trong `float` hoặc `double` và ảnh hưởng tới độ chính xác như thế nào?
Bạn nhận diện underflow trong phép nhân hoặc chia số thực rất nhỏ và kiểm tra trường hợp kết quả bị làm tròn về không ra sao?
Bạn xác định tình huống overflow thành giá trị vô cực trong số thực và lựa chọn chiến lược xử lý như thế nào?
Bạn phân biệt rounding mode mặc định của phép toán dấu phẩy động với các chính sách làm tròn nghiệp vụ như thế nào?
Bạn giải thích tác động của `Math.fma` tới số lần làm tròn và độ chính xác của phép nhân cộng như thế nào?
Bạn sử dụng `Math.nextUp`, `nextDown` và `nextAfter` để khảo sát giá trị số thực lân cận trong kiểm thử biên ra sao?
Bạn so sánh `Math` và `StrictMath` khi cần tái lập kết quả số học giữa các nền tảng như thế nào?
Bạn thiết kế thuật toán cộng dồn như Kahan summation để giảm mất mát độ chính xác khi cộng nhiều số có độ lớn khác nhau ra sao?
Bạn kiểm chứng sai số của phép tính trung bình khi cộng các giá trị rất lớn và rất nhỏ trong cùng một tập dữ liệu như thế nào?
Bạn giải thích vì sao thay đổi thứ tự tính tổng trong parallel stream có thể làm kết quả dấu phẩy động thay đổi ra sao?
Bạn xác định trường hợp cần dùng phép toán so sánh hoặc thứ tự toàn phần qua `Double.compare` khi sắp xếp collection ra sao?
Bạn phân biệt `Math.round`, `Math.floor`, `Math.ceil` và `Math.rint` về quy tắc làm tròn và kiểu giá trị trả về như thế nào?
Bạn thiết kế xử lý các trường hợp làm tròn số âm hoặc giá trị nằm chính giữa hai số nguyên theo yêu cầu nghiệp vụ ra sao?
Bạn lựa chọn kiểu dữ liệu cho tọa độ, đo lường vật lý hoặc mô phỏng số dựa trên giới hạn sai số và hiệu năng như thế nào?
Bạn giải thích khi nào `BigInteger` phù hợp hơn `long` và tác động của độ chính xác tùy ý lên chi phí tính toán ra sao?
Bạn tạo một `BigInteger` từ chuỗi hoặc từ dữ liệu nhị phân có dấu và kiểm tra cách biểu diễn bù hai như thế nào?
Bạn phân biệt các phương thức số học bất biến của `BigInteger` với toán tử số học trên kiểu nguyên thủy như thế nào?
Bạn xử lý chuyển `BigInteger` sang `long` bằng `longValueExact` để tránh cắt cụt phần giá trị như thế nào?
Bạn thiết kế phép toán `BigInteger` có dữ liệu đầu vào rất lớn sao cho không làm cạn CPU hoặc bộ nhớ như thế nào?
Bạn lựa chọn `BigInteger.gcd`, `modPow` hoặc `modInverse` trong các thuật toán số nguyên và xác định tiền điều kiện cần kiểm tra ra sao?
Bạn phân biệt kết quả của `BigInteger.mod` với `remainder` khi làm việc với số âm và modulus dương như thế nào?
Bạn xác định khi nào `BigInteger.isProbablePrime` phù hợp và đánh giá mức bảo đảm của tham số certainty như thế nào?
Bạn kiểm tra tác động của bit length và số lượng phép toán lên hiệu năng `BigInteger` trong một dịch vụ xử lý dữ liệu lớn ra sao?
Bạn giải thích cấu trúc unscaled value và scale của `BigDecimal` khi biểu diễn số thập phân chính xác như thế nào?
Bạn phân biệt cách khởi tạo `BigDecimal` từ chuỗi, từ `double` và qua `BigDecimal.valueOf` về độ chính xác như thế nào?
Bạn xác định vì sao `new BigDecimal(0.1)` có thể tạo ra giá trị không như người dùng mong đợi như thế nào?
Bạn giải thích cách `BigDecimal.add`, `subtract` và `multiply` quyết định scale của kết quả trong những trường hợp thường gặp ra sao?
Bạn chọn `RoundingMode` cho phép tính tiền hoặc số liệu báo cáo mà vẫn tuân theo chính sách nghiệp vụ như thế nào?
Bạn phân biệt `RoundingMode.HALF_UP`, `HALF_EVEN`, `DOWN`, `FLOOR` và `CEILING` khi làm tròn số âm hoặc số giữa hai mốc ra sao?
Bạn xử lý `ArithmeticException` khi chia hai `BigDecimal` cho kết quả thập phân vô hạn mà không truyền rounding mode như thế nào?
Bạn quyết định khi nào dùng `divide` với scale và rounding mode, khi nào dùng `MathContext` để kiểm soát precision ra sao?
Bạn giải thích sự khác biệt giữa precision và scale của `BigDecimal` khi giới hạn số chữ số có nghĩa như thế nào?
Bạn đánh giá ảnh hưởng của `MathContext.DECIMAL64` hoặc precision tùy chọn đến kết quả của chuỗi phép tính ra sao?
Bạn phân biệt `BigDecimal.equals` với `compareTo` đối với các giá trị có scale khác nhau và tác động tới `HashSet` hoặc `TreeSet` như thế nào?
Bạn lựa chọn có nên chuẩn hóa scale trước khi dùng `BigDecimal` làm khóa `Map` để tránh hai cách biểu diễn giá trị bằng nhau như thế nào?
Bạn giải thích hệ quả của `stripTrailingZeros` đối với scale và cách xuất chuỗi của `BigDecimal` ra sao?
Bạn phân biệt `toString`, `toPlainString` và `toEngineeringString` khi serialize `BigDecimal` vào hệ thống khác như thế nào?
Bạn kiểm soát việc dùng `setScale` sao cho không vô tình làm tròn hoặc thay đổi giá trị tiền tệ ngoài yêu cầu nghiệp vụ ra sao?
Bạn phân biệt phép chia thực sự với `divideToIntegralValue` và `remainder` khi thao tác trên `BigDecimal` như thế nào?
Bạn xử lý chuyển đổi `BigDecimal` sang `int` hoặc `long` bằng các phương thức exact và xác định khi nào chuyển đổi bị từ chối ra sao?
Bạn so sánh `BigDecimal` với số nguyên biểu diễn đơn vị nhỏ nhất của tiền tệ khi thiết kế hệ thống thanh toán như thế nào?
Bạn thiết kế phép tính chiết khấu, thuế và tổng tiền sao cho quy tắc làm tròn nhất quán ở từng bước như thế nào?
Bạn xây dựng chính sách phân bổ phần tiền lẻ khi chia một khoản tiền cho nhiều người mà tổng các phần phải bằng tổng gốc như thế nào?
Bạn xác định cách lưu `BigDecimal` trong cơ sở dữ liệu qua kiểu DECIMAL hoặc NUMERIC để tránh mất độ chính xác ra sao?
Bạn kiểm tra serialization JSON của số nguyên lớn và `BigDecimal` khi client JavaScript có thể không giữ được toàn bộ chữ số như thế nào?
Bạn phân biệt giá trị số và chuỗi định dạng theo locale khi truyền dữ liệu tài chính qua REST API như thế nào?
Bạn giải thích ảnh hưởng của `NumberFormat` và `DecimalFormat` tới việc hiển thị `BigDecimal` mà không làm thay đổi giá trị lưu trữ như thế nào?
Bạn xác định số chữ số thập phân hợp lệ theo đơn vị đo hoặc đồng tiền thay vì áp dụng một scale cố định cho mọi dữ liệu ra sao?
Bạn thiết kế kiểm thử property-based cho phép cộng và nhân số nguyên có kiểm tra overflow với nhiều giá trị biên như thế nào?
Bạn tạo bộ kiểm thử gồm `NaN`, vô cực, số âm không, số rất nhỏ và số rất lớn để đánh giá một thuật toán `double` ra sao?
Bạn xây dựng kiểm thử so sánh số thực dựa trên sai số cho phép và phát hiện sự khác nhau giữa dữ liệu đầu vào và sai số thuật toán như thế nào?
Bạn kiểm thử các chế độ làm tròn `BigDecimal` trên giá trị dương, âm và giá trị đúng giữa hai mốc như thế nào?
Bạn dùng benchmark để so sánh thao tác trên `long`, `double`, `BigInteger` và `BigDecimal` mà không bị nhiễu do JIT hoặc boxing ra sao?
Bạn lựa chọn chiến lược chống tràn số, chống mất chính xác và bảo vệ tài nguyên khi nhận dữ liệu số không tin cậy từ bên ngoài như thế nào?
Bạn xây dựng tiêu chí lựa chọn kiểu số và chính sách rounding cho từng trường dữ liệu trong một hệ thống Java lớn như thế nào?
