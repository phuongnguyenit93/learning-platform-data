Câu 1. Với `Locale.forLanguageTag("pt-BR")`, cặp giá trị trả về nào đúng?
A. `getLanguage()` là `BR` và `getCountry()` là `pt`
B. `getLanguage()` là `pt` và `getCountry()` là `BR`
C. `getLanguage()` là `pt-BR` và `getCountry()` rỗng
D. `getLanguage()` là `pt` và `getVariant()` là `BR`
Đáp án đúng: B

Câu 2. Với `Locale.forLanguageTag("zh-Hant-TW")`, script và region lần lượt là gì?
A. Script `Hant`, region `TW`
B. Script `Hant` và region `zh`
C. Script `TW` và region `Hant`
D. Script `zh` và region `Hant`
Đáp án đúng: A

Câu 3. Để tạo locale ngôn ngữ `sr`, script `Latn` và region `RS`, API nào thích hợp?
A. `Locale.Builder` với `setLanguage`, `setRegion`, `setVariant`
B. `Locale.Builder` với `setLanguage`, `setCountry`, `setScript`
C. `Locale.Builder` với `setLanguage`, `setVariant`, `setCountry`
D. `Locale.Builder` với `setLanguage`, `setScript`, `setRegion`
Đáp án đúng: D

Câu 4. `Locale.getDefault(Locale.Category.DISPLAY)` dùng để lấy cấu hình gì?
A. Locale mặc định phục vụ định dạng số và ngày giờ
B. Locale mặc định cho tên ngôn ngữ và vùng hiển thị
C. Locale mặc định phục vụ giải mã byte của tệp văn bản
D. Locale mặc định phục vụ xác định múi giờ hệ thống
Đáp án đúng: B

Câu 5. `Locale.getDefault(Locale.Category.FORMAT)` ưu tiên cho trường hợp nào?
A. Chọn locale mặc định khi hiển thị tên ngôn ngữ
B. Chọn charset mặc định khi mã hóa một chuỗi ký tự
C. Chọn locale mặc định khi định dạng số và ngày
D. Chọn múi giờ mặc định khi định dạng một `Instant`
Đáp án đúng: C

Câu 6. Đặc điểm của `Locale.ROOT` trong Java là gì?
A. Locale luôn tương ứng với tiếng Anh không có vùng
B. Locale trung lập, mã ngôn ngữ và quốc gia đều rỗng
C. Locale mặc định lấy theo cấu hình vùng miền máy chủ
D. Locale luôn tương ứng với tiếng Anh tại Hoa Kỳ
Đáp án đúng: B

Câu 7. Với locale có ngôn ngữ `vi` và vùng `VN`, `toLanguageTag()` biểu diễn theo dạng nào?
A. Tên vùng hiển thị dạng `Vietnam`
B. Chuỗi mã vùng trước dạng `VN-vi`
C. Chuỗi dấu gạch dưới dạng `vi_VN`
D. Thẻ BCP 47 theo dạng `vi-VN`
Đáp án đúng: D

Câu 8. Gọi `Locale.setDefault(Locale.FRANCE)` thường tác động đến phạm vi nào?
A. Locale mặc định của tiến trình JVM đang chạy
B. Locale mặc định của hệ điều hành cho mọi ứng dụng
C. Locale cố định của riêng đối tượng gọi phương thức
D. Locale đã lưu trong mọi file `.properties` của dự án
Đáp án đúng: A

Câu 9. Với chữ `i`, `"i".toUpperCase(Locale.forLanguageTag("tr-TR"))` thường trả gì?
A. Chữ `İ` hoa có dấu chấm theo quy tắc tiếng Thổ
B. Chữ `I` hoa không dấu chấm theo quy tắc tiếng Anh
C. Chữ `ı` thường không dấu chấm theo tiếng Thổ
D. Chữ `i` thường giữ nguyên vì không đổi chữ hoa
Đáp án đúng: A

Câu 10. Vì sao nên dùng `Locale.ROOT` khi chuẩn hóa chữ hoa/thường của mã định danh kỹ thuật?
A. Tự phát hiện ngôn ngữ người dùng trước khi đổi chữ
B. Thực hiện so sánh chuỗi theo cách sắp xếp tiếng Việt
C. Đổi chữ theo quy tắc độc lập với locale người dùng
D. Tự thay ký tự Unicode thành byte ASCII trước khi lưu
Đáp án đúng: C

Câu 11. Giả sử tệp `Messages_vi_VN.properties` tồn tại, `getBundle("Messages", vi_VN)` ưu tiên tài nguyên nào?
A. Ưu tiên `Messages_vi.properties` vì bỏ qua region
B. Ưu tiên `Messages_en_US.properties` theo ngôn ngữ JVM
C. Ưu tiên `Messages_vi_VN.properties` theo locale yêu cầu
D. Ưu tiên `Messages.properties` bất kể locale yêu cầu
Đáp án đúng: C

Câu 12. Khi khóa thiếu trong `Messages_vi_VN` nhưng có ở cha `Messages_vi`, `ResourceBundle` thường làm gì?
A. Ném lỗi ngay khi bundle chi tiết thiếu khóa
B. Tìm giá trị qua bundle cha `Messages_vi`
C. Chỉ tìm khóa trong bundle `Messages.properties`
D. Chuyển toàn bộ bundle sang locale mặc định JVM
Đáp án đúng: B

Câu 13. Khi `getString("title")` không tìm được khóa trong chuỗi bundle, kết quả nào đúng?
A. Ném `MissingResourceException` khi truy xuất khóa
B. Trả `null` khi truy xuất khóa không tồn tại
C. Trả chuỗi `title` như giá trị mặc định của khóa
D. Trả chuỗi rỗng và tiếp tục chạy như bình thường
Đáp án đúng: A

Câu 14. Base name `com.example.i18n.Messages` tương ứng vị trí tệp `.properties` nào?
A. Đường dẫn `com/example/i18n/Messages.properties`
B. Đường dẫn `com/example/i18n.properties/Messages`
C. Đường dẫn `com.example.i18n/Messages.properties`
D. Đường dẫn `Messages/com/example/i18n.properties`
Đáp án đúng: A

Câu 15. Ý nghĩa của `ResourceBundle.getLocale()` trên bundle đã tải là gì?
A. Cho biết locale được truyền vào dù đã fallback
B. Cho biết locale của luồng đang gọi `getString`
C. Cho biết locale của bundle thực tế được tìm thấy
D. Cho biết locale mặc định hiện tại của hệ điều hành
Đáp án đúng: C

Câu 16. Từ Java 9, khi không tùy chỉnh cấu hình, `PropertyResourceBundle` đọc dữ liệu tệp bằng cách nào?
A. Luôn dùng UTF-16LE rồi fallback sang UTF-8
B. Thử UTF-8 và có thể fallback sang ISO-8859-1
C. Luôn dùng charset mặc định của hệ điều hành
D. Chỉ cho phép ký tự ASCII không dấu trong tệp
Đáp án đúng: B

Câu 17. Nếu `ListResourceBundle` chứa một giá trị không phải `String`, nên lấy giá trị đó bằng API nào?
A. Dùng `getString(key)` để ép giá trị thành chuỗi
B. Dùng `getObject(key)` để lấy giá trị dạng `Object`
C. Dùng `getStringArray(key)` để trả bất kỳ object
D. Dùng `toString()` để lấy đúng giá trị theo khóa
Đáp án đúng: B

Câu 18. Khi chỉnh sửa file bundle nhưng JVM đang cache dữ liệu cũ, API nào có thể xóa cache?
A. Gọi `System.gc()` để xóa toàn bộ bundle cache
B. Gọi `Locale.setDefault()` để xóa bundle cache
C. Gọi `MessageFormat.format()` để xóa bundle cache
D. Gọi `ResourceBundle.clearCache()` để xóa bundle cache
Đáp án đúng: D

Câu 19. Trong pattern `"Xin chào {0}, mã {1}"` của `MessageFormat`, số `0` và `1` đại diện cho gì?
A. Chỉ số đối số truyền vào, tính từ phần tử đầu tiên
B. Vị trí dòng văn bản để ngắt trước khi hiển thị
C. Số lần lặp lại định dạng của chuỗi đầu vào
D. Thứ tự locale ưu tiên khi tìm trong bundle cha
Đáp án đúng: A

Câu 20. Để hiển thị dấu nháy đơn thật trong `MessageFormat` pattern, cách phổ biến là gì?
A. Viết dấu nháy đơn hai lần liền nhau `''`
B. Đặt ký tự gạch chéo ngược trước dấu nháy `\'`
C. Đặt ký tự dấu phần trăm trước dấu nháy `%'`
D. Đặt ký tự dấu ngoặc kép trước dấu nháy `"'`
Đáp án đúng: A

Câu 21. Cách nào thiết lập locale trực tiếp cho một đối tượng `MessageFormat`?
A. Khởi tạo `new MessageFormat(locale, pattern)`
B. Khởi tạo `new MessageFormat(pattern, charset)`
C. Khởi tạo `new MessageFormat(pattern, locale)`
D. Khởi tạo `new MessageFormat(charset, locale)`
Đáp án đúng: C

Câu 22. Với pattern `"{0,number}"`, `MessageFormat` định dạng đối số số bằng gì?
A. Bằng định dạng số phụ thuộc locale của MessageFormat
B. Bằng mã chữ số ASCII bất kể locale đang dùng
C. Bằng biểu diễn nhị phân cố định của đối số số
D. Bằng tên ngôn ngữ trong locale của MessageFormat
Đáp án đúng: A

Câu 23. Với pattern `"{0,date,short}"`, đối số nào tương thích với bộ định dạng ngày mặc định?
A. Chuỗi ISO 8601 truyền thẳng vào vị trí số 0
B. Đường dẫn `java.nio.file.Path` truyền vào vị trí 0
C. Đối tượng `java.time.LocalDate` truyền vào vị trí 0
D. Đối tượng `java.util.Date` truyền vào vị trí số 0
Đáp án đúng: D

Câu 24. Trong `MessageFormat`, kiểu `choice` được dùng để làm gì?
A. Chọn charset theo dấu hiệu byte của đầu vào
B. Chọn timezone theo định dạng giờ đã truyền
C. Chọn mẫu văn bản theo giá trị số của đối số
D. Chọn tên tệp bundle theo đường dẫn tài nguyên
Đáp án đúng: C

Câu 25. Khi tái sử dụng `MessageFormat` qua nhiều luồng, lưu ý nào phù hợp?
A. Đối tượng immutable, có thể sửa không đồng bộ
B. Mỗi đối tượng tự tạo một luồng xử lý độc lập
C. JVM tự sao chép đối tượng khi nhiều luồng gọi
D. Đối tượng mutable, cần đồng bộ nếu dùng chung
Đáp án đúng: D

Câu 26. `NumberFormat.getNumberInstance(Locale.GERMANY)` với `1234.5` thường hiển thị thế nào?
A. Dùng dấu chấm phân nhóm và dấu chấm thập phân
B. Dùng dấu chấm phân nhóm và dấu phẩy thập phân
C. Dùng dấu phẩy phân nhóm và dấu chấm thập phân
D. Dùng dấu cách phân nhóm và dấu chấm thập phân
Đáp án đúng: B

Câu 27. `NumberFormat.getPercentInstance(Locale.US).format(0.25)` thường trả gì?
A. Chuỗi `250%` nhân thêm một bậc khi hiển thị
B. Chuỗi `25%` biểu diễn một phần tư dưới dạng phần trăm
C. Chuỗi `0.25` bỏ qua mọi ký hiệu phần trăm
D. Chuỗi `0.25%` giữ nguyên trị số rồi thêm dấu phần trăm
Đáp án đúng: B

Câu 28. `NumberFormat.getCurrencyInstance(locale)` có tự chuyển đổi tỷ giá giữa các tiền tệ không?
A. Tự truy vấn tỷ giá mới nhất rồi đổi sang tiền địa phương
B. Tự nhân tỷ giá mặc định tích hợp trong bộ JDK
C. Chỉ định dạng giá trị, không tự đổi tiền theo tỷ giá
D. Tự chuyển đổi chính xác nếu locale khác vùng tiền
Đáp án đúng: C

Câu 29. `Currency.getInstance(Locale.JAPAN).getCurrencyCode()` thông thường trả mã nào?
A. Mã tiền tệ `JPN` theo chuẩn ISO 4217
B. Mã tiền tệ `YEN` theo chuẩn ISO 4217
C. Mã tiền tệ `JP` theo chuẩn ISO 4217
D. Mã tiền tệ `JPY` theo chuẩn ISO 4217
Đáp án đúng: D

Câu 30. Dùng API nào lấy các ký hiệu phân nhóm và thập phân theo locale cho `DecimalFormat`?
A. `CurrencyFormatSymbols.getInstance(locale)`
B. `DecimalFormatSymbols.getInstance(locale)`
C. `DecimalFormat.getInstance(locale)`
D. `NumberFormatSymbols.getInstance(locale)`
Đáp án đúng: B

Câu 31. Với `NumberFormat.setParseIntegerOnly(true)`, điều nào đúng?
A. Buộc định dạng luôn làm tròn mọi phần thập phân
B. Buộc trình parse từ chối tất cả chuỗi có dấu phẩy
C. Chỉ điều chỉnh cách format, không thay đổi cách parse
D. Chỉ điều chỉnh cách parse, không thay đổi cách format
Đáp án đúng: D

Câu 32. Với `NumberFormat` có một chữ số thập phân và `HALF_UP`, giá trị `1.25` thành gì?
A. Giá trị `1.2` khi làm tròn đến một chữ số
B. Giá trị `1.25` khi giữ cả hai chữ số
C. Giá trị `2.0` khi làm tròn đến số nguyên
D. Giá trị `1.3` khi làm tròn đến một chữ số
Đáp án đúng: D

Câu 33. Khi nhiều luồng cần dùng cùng một `NumberFormat`, khuyến nghị nào đúng?
A. Không giả định thread-safe; dùng riêng hoặc đồng bộ
B. Có thể sửa pattern tùy ý từ các luồng song song
C. Không cần đồng bộ vì mọi thuộc tính đều immutable
D. Chỉ cần gọi `format` một lần để khóa đối tượng
Đáp án đúng: A

Câu 34. Để format ngày theo vùng miền với `DateTimeFormatter`, cách nào phù hợp?
A. `ofLocalizedDate(style).withCharset(locale)`
B. `ofLocalizedDate(style).withZone(locale)`
C. `ofLocalizedDate(style).withFormat(locale)`
D. `ofLocalizedDate(style).withLocale(locale)`
Đáp án đúng: D

Câu 35. Phát biểu nào đúng về `DateTimeFormatter` so với `SimpleDateFormat`?
A. `SimpleDateFormat` immutable và thread-safe
B. `SimpleDateFormat` luôn dùng UTC để định dạng
C. `DateTimeFormatter` mutable và không thread-safe
D. `DateTimeFormatter` immutable và thread-safe
Đáp án đúng: D

Câu 36. Với pattern `"d MMMM uuuu"` của `DateTimeFormatter`, locale ảnh hưởng phần nào rõ nhất?
A. Trị số năm từ ký hiệu `uuuu` theo timezone
B. Số ngày trong tháng từ ký hiệu `d` theo charset
C. Ngôn ngữ của tên tháng từ ký hiệu `MMMM`
D. Số đối tượng `LocalDate` được tạo khi format
Đáp án đúng: C

Câu 37. `LocalDate` khác `ZonedDateTime` chủ yếu ở thông tin nào?
A. `LocalDate` luôn giữ giờ và vùng thời gian
B. `LocalDate` không giữ giờ và vùng thời gian
C. `LocalDate` luôn lưu offset UTC của hệ thống
D. `LocalDate` lưu giờ nhưng không lưu ngày
Đáp án đúng: B

Câu 38. Muốn format một `Instant` bằng pattern có trường giờ địa phương, cần cấu hình gì cho formatter?
A. Đặt pattern qua `withPattern(String)`
B. Đặt locale qua `withLocale(Locale)`
C. Đặt zone qua `withZone(ZoneId)`
D. Đặt charset qua `withCharset(Charset)`
Đáp án đúng: C

Câu 39. Để chọn ký hiệu chữ số và dấu âm của `DateTimeFormatter`, API nào trực tiếp phù hợp?
A. Dùng `withResolverStyle(ResolverStyle)`
B. Dùng `withZone(ZoneId)` để chọn vùng giờ
C. Dùng `withDecimalStyle(DecimalStyle)`
D. Dùng `withChronology(Chronology)`
Đáp án đúng: C

Câu 40. Đối với chuỗi Java chứa một emoji ngoài BMP như `"😀"`, `length()` thông thường bằng gì?
A. Giá trị `2` vì chuỗi dùng hai UTF-16 code unit
B. Giá trị `1` vì chuỗi chỉ có một Unicode code point
C. Giá trị `4` vì UTF-8 dùng bốn byte cho emoji
D. Giá trị `0` vì emoji không phải ký tự chữ cái
Đáp án đúng: A

Câu 41. Muốn đếm Unicode code point của chuỗi có surrogate pair, API nào đúng?
A. Phương thức `length()` trên chuỗi gốc
B. Phương thức `codePointCount(0, length())`
C. Phương thức `getBytes().length` trên chuỗi
D. Phương thức `charAt(0)` trên chuỗi
Đáp án đúng: B

Câu 42. `Normalizer.normalize(text, Normalizer.Form.NFC)` có mục tiêu nào?
A. Sắp xếp các chữ cái theo thứ tự locale
B. Loại bỏ mọi dấu thanh của tiếng Việt khỏi chuỗi
C. Chuẩn hóa Unicode theo dạng ghép chính tắc
D. Chuyển mọi ký tự có dấu thành bảng mã ASCII
Đáp án đúng: C

Câu 43. Để so sánh chuỗi phục vụ sắp xếp theo locale, API nào thích hợp?
A. Dùng `Collator.getInstance(locale).compare(a,b)`
B. Dùng `Arrays.compare(a,b)` để xét ngôn ngữ hiện tại
C. Dùng `Objects.equals(a,b)` để xét thứ tự theo locale
D. Dùng `String.compareTo(a,b)` theo locale mặc định
Đáp án đúng: A

Câu 44. `BreakIterator.getWordInstance(locale)` hỗ trợ công việc nào?
A. Chuyển tất cả từ sang chữ hoa theo vùng/ngôn ngữ
B. Thay các từ bằng bản dịch theo vùng/ngôn ngữ
C. Xác định ranh giới từ theo quy tắc vùng/ngôn ngữ
D. Thêm dấu câu vào mỗi từ theo vùng/ngôn ngữ
Đáp án đúng: C

Câu 45. Vai trò phù hợp của lớp `java.text.Bidi` trong xử lý giao diện đa ngôn ngữ là gì?
A. Tự động dịch các đoạn RTL sang tiếng địa phương
B. Phân tích hướng hiển thị khi văn bản trộn RTL và LTR
C. Mã hóa các ký tự RTL thành byte trong định dạng UTF-8
D. Loại bỏ ký tự điều khiển hướng trong mọi đoạn văn
Đáp án đúng: B

Câu 46. `text.getBytes(StandardCharsets.UTF_8)` thực hiện phép chuyển đổi nào?
A. Mã hóa chuỗi ký tự thành các byte theo UTF-8
B. Kiểm tra thứ tự sắp xếp ngôn ngữ của chuỗi ký tự
C. Giải mã mảng byte thành chuỗi ký tự theo UTF-8
D. Chuyển chuỗi ký tự sang locale của hệ điều hành
Đáp án đúng: A

Câu 47. `new String(bytes, StandardCharsets.UTF_8)` thực hiện việc nào?
A. Chuyển byte đầu vào thành chuỗi chỉ có chữ ASCII
B. Đổi locale của máy ảo trước khi tạo chuỗi ký tự
C. Mã hóa ký tự đầu vào thành byte mới bằng UTF-8
D. Giải mã byte đầu vào thành chuỗi Unicode bằng UTF-8
Đáp án đúng: D

Câu 48. Để kiểm thử thông báo đa ngôn ngữ ổn định giữa các máy, nên làm gì?
A. Dựa vào locale và vùng giờ mặc định của máy chạy
B. Chỉ kiểm thử với ngôn ngữ mặc định của lập trình viên
C. Giả sử mọi locale dùng cùng thứ tự ngày và dấu thập phân
D. Chỉ định locale và vùng giờ cụ thể trong kiểm thử
Đáp án đúng: D
