Câu 1. Với `String s = "ab"; s.concat("c");`, giá trị của `s` sau đó là gì?
A. Thành `"c"` vì concat thay thế chuỗi cũ bằng tham số.
B. Thành `null` vì kết quả concat không được giữ trong biến.
C. Thành `"abc"` vì concat thay đổi nội dung của String gốc.
D. Vẫn là `"ab"` vì kết quả concat không được gán lại.
Đáp án đúng: D

Câu 2. Biểu thức `"ja" + "va" == "java"` có giá trị nào trong Java?
A. `true` vì JVM so nội dung hai String khi dùng toán tử ==.
B. `false` vì toán tử `==` không áp dụng cho kiểu String.
C. `true` vì phép nối hằng được gộp ở compile time.
D. `false` vì phép nối luôn tạo một String mới ở runtime.
Đáp án đúng: C

Câu 3. Với `String a = new String("cat"); String b = "cat";`, nhận định nào đúng?
A. Cả `equals` và `==` đều true do nội dung giống nhau.
B. `equals` true, `==` false vì a và b khác tham chiếu.
C. `equals` false, `==` true do String a lấy từ pool.
D. Cả `equals` và `==` đều false vì a được tạo bằng new.
Đáp án đúng: B

Câu 4. Với `String s = new String("hi").intern();`, điều gì đúng về `s`?
A. `s == "hi"` false vì intern chỉ trả về bản sao không nằm trong pool.
B. `s.length()` bằng 0 vì intern chỉ lưu metadata của chuỗi.
C. `s == "hi"` true vì intern trả tham chiếu canonical trong pool.
D. `s.equals("hi")` false vì intern thay đổi các ký tự gốc.
Đáp án đúng: C

Câu 5. Với `String x = "a"; String y = x + "b";`, nhận định nào đúng về `y`?
A. `y.equals("ab")` true và `y == "ab"` false trong tình huống này.
B. `y.equals("ab")` false và `y == "ab"` false vì phép nối không hợp lệ.
C. `y.equals("ab")` true và `y == "ab"` true vì x là String.
D. `y.equals("ab")` false và `y == "ab"` true vì literal được intern.
Đáp án đúng: A

Câu 6. Giá trị của biểu thức `"Java".equals("java")` là gì?
A. `true` vì `equals` so nội dung không xét chữ hoa.
B. `false` vì `equals` chỉ áp dụng cho cùng tham chiếu.
C. `true` vì hai String được chuẩn hóa sang chữ thường.
D. `false` vì `equals` phân biệt chữ hoa và chữ thường.
Đáp án đúng: D

Câu 7. Khi cần chuyển chuỗi thành chữ thường không phụ thuộc locale mặc định của máy, nên dùng gì?
A. Dùng `s.toUpperCase(Locale.ROOT)` để tạo chữ thường theo chuẩn chung.
B. Dùng `s.toLowerCase()` vì nó mặc định ép dùng Locale.ROOT.
C. Dùng `s.toLowerCase(Locale.getDefault())` để loại bỏ ảnh hưởng locale.
D. Dùng `s.toLowerCase(Locale.ROOT)` để không lệ thuộc locale máy.
Đáp án đúng: D

Câu 8. Với `String s = "😀";`, `s.length()` trả giá trị nào trên Java?
A. `2` vì emoji ngoài BMP cần hai đơn vị UTF-16.
B. `1` vì String.length đếm các Unicode code point đầy đủ.
C. `4` vì emoji được mã hóa thành bốn byte UTF-8 thông thường.
D. `0` vì emoji không phải ký tự thuộc bảng mã Latin-1.
Đáp án đúng: A

Câu 9. Với `String s = "😀";`, `s.codePointCount(0, s.length())` trả về gì?
A. `2` vì phương thức đếm các đơn vị char trong UTF-16.
B. `1` vì cặp surrogate biểu diễn một Unicode code point.
C. `0` vì emoji nằm ngoài Basic Multilingual Plane.
D. `4` vì phương thức đếm số byte UTF-8 của emoji.
Đáp án đúng: B

Câu 10. Với `String s = "😀";`, nhận định nào đúng về `s.charAt(0)`?
A. Trả về `char` high surrogate, không phải toàn bộ emoji.
B. Trả về `int` mang Unicode code point U+1F600 đầy đủ.
C. Trả về `String` chứa một ký tự emoji hoàn chỉnh.
D. Trả về byte đầu tiên trong chuỗi mã hóa UTF-8.
Đáp án đúng: A

Câu 11. Với `String s = "😀A";`, giá trị `s.offsetByCodePoints(0, 1)` là gì?
A. `2`, vị trí UTF-16 ngay sau cặp surrogate emoji.
B. `4`, là số byte UTF-8 dùng để mã hóa emoji.
C. `1`, là vị trí UTF-16 của low surrogate trong emoji.
D. `3`, là tổng số UTF-16 code unit của cả chuỗi.
Đáp án đúng: A

Câu 12. Với `"ABCDE".substring(1, 3)`, kết quả là chuỗi nào?
A. `"BCD"` do cả chỉ số bắt đầu và kết thúc đều được lấy.
B. `"AB"` do substring bắt đầu từ ký tự thứ nhất.
C. `"CD"` do substring bắt đầu sau chỉ số đầu vào.
D. `"BC"`, lấy từ index 1 nhưng không lấy index 3.
Đáp án đúng: D

Câu 13. Với `"banana".indexOf("na")`, kết quả là chỉ số nào?
A. `1`, vị trí chữ a xuất hiện trước cụm `na` đầu tiên.
B. `4`, vị trí bắt đầu của lần xuất hiện `na` cuối cùng.
C. `2`, vị trí bắt đầu của lần xuất hiện `na` đầu tiên.
D. `-1`, vì String.indexOf chỉ nhận một ký tự char.
Đáp án đúng: C

Câu 14. Với `"banana".lastIndexOf("na")`, kết quả là chỉ số nào?
A. `5`, nơi ký tự cuối của chuỗi banana nằm.
B. `2`, nơi cụm `na` xuất hiện đầu tiên trong chuỗi.
C. `-1`, do lastIndexOf chỉ hỗ trợ một ký tự char.
D. `4`, vị trí bắt đầu của cụm `na` cuối cùng.
Đáp án đúng: D

Câu 15. Kết quả của `"hello".contains("He")` trong Java là gì?
A. `true` vì chuỗi con được chuẩn hóa thành chữ thường.
B. `false` vì contains chỉ tìm được chuỗi có cùng độ dài.
C. `true` vì contains bỏ qua sự khác nhau về chữ hoa thường.
D. `false` vì contains phân biệt hoa và thường.
Đáp án đúng: D

Câu 16. Kết quả của `"\u2003hi\u2003".strip()` là gì, với `\u2003` là EM SPACE?
A. `"hi"` vì strip loại bỏ Unicode whitespace ở hai đầu.
B. `"hi\u2003"` vì strip chỉ xử lý whitespace phía trước.
C. `"\u2003hi"` vì strip không bỏ whitespace phía trước.
D. `"\u2003hi\u2003"` vì strip giữ lại khoảng EM SPACE.
Đáp án đúng: A

Câu 17. Với `String s = " \t ";`, biểu thức `s.isBlank()` có kết quả nào?
A. `true` vì isBlank tự gọi trim rồi xóa nội dung String gốc.
B. `false` vì tab ngăn isBlank xem s là toàn khoảng trắng.
C. `true` vì khoảng trắng và tab đều là whitespace ở đây.
D. `false` vì isBlank chỉ đúng với String có length bằng 0.
Đáp án đúng: C

Câu 18. Khi nối nhiều mảnh văn bản trong vòng lặp một luồng, `StringBuilder` có ưu điểm gì?
A. `append` thay đổi builder, tránh tạo String mới mỗi lượt.
B. `append` đồng bộ hóa từng thao tác để nhiều thread cùng ghi.
C. `append` buộc JVM mã hóa dữ liệu dưới dạng UTF-8 bytes.
D. `append` tự động intern mọi chuỗi mới tạo trong string pool.
Đáp án đúng: A

Câu 19. Điểm khác biệt cơ bản giữa `StringBuilder` và `StringBuffer` là gì?
A. `StringBuffer` immutable nên append trả ra object mới.
B. `StringBuffer` đồng bộ method; `StringBuilder` thì không.
C. `StringBuilder` đồng bộ từng thao tác còn Buffer thì không.
D. `StringBuilder` lưu char, còn Buffer bắt buộc lưu UTF-8.
Đáp án đúng: B

Câu 20. Với `StringBuilder b = new StringBuilder("A"); b.append((String) null);`, kết quả b.toString() là gì?
A. `"A0"` vì null được chuyển sang ký tự số 0 khi nối.
B. `"A"` vì append(String) bỏ qua đối số có giá trị null.
C. `"Anull"` vì append(String) chuyển null thành chữ `null`.
D. `"A"` rồi ném NullPointerException ngay khi gọi append.
Đáp án đúng: C

Câu 21. Với biểu thức `"ha".repeat(3)`, kết quả chuỗi nào là đúng?
A. `"hhh"` vì repeat chỉ lặp ký tự đầu tiên.
B. `"hahaha"` vì nội dung ha được lặp lại ba lần.
C. `"haha"` vì repeat tính tổng số chuỗi bằng 3 gồm gốc.
D. `"ha3"` vì repeat ghép đối số vào cuối String.
Đáp án đúng: B

Câu 22. Kết quả của `String.join("|", "red", "blue")` là gì?
A. `"red,blue"` vì join dùng dấu phẩy khi các phần tử là String.
B. `"redblue|"` vì delimiter được nối vào sau phần tử cuối.
C. `"|red|blue|"` vì delimiter được thêm cả đầu lẫn cuối.
D. `"red|blue"` vì ký tự phân tách đặt giữa hai phần tử.
Đáp án đúng: D

Câu 23. Với `String.format(Locale.US, "%.2f", 1.5)`, kết quả là gì?
A. `"1,50"` vì formatter dùng dấu phẩy theo Locale.US.
B. `"1.5"` vì định dạng %.2f không thêm chữ số 0.
C. `"1.50"` vì %.2f in hai số lẻ theo Locale.US.
D. `"1.500"` vì %.2f làm tròn đến ba chữ số thập phân.
Đáp án đúng: C

Câu 24. Trong `"a.b".replace(".", "-")`, dấu chấm được hiểu như thế nào?
A. Regex wildcard, nên kết quả là `"---"`.
B. Chuỗi literal `"."`, nên kết quả là `"a-b"`.
C. Regex chỉ định mọi dấu cách, nên kết quả là `"a.b"`.
D. Regex chỉ định cuối dòng, nên chuỗi vẫn là `"a.b"`.
Đáp án đúng: B

Câu 25. Với `"a.b".replaceAll(".", "-")`, kết quả nào đúng?
A. `"---"` vì dấu chấm regex match từng ký tự.
B. `"a.b"` vì replaceAll chỉ tìm ở cuối chuỗi.
C. `"a-b"` vì replaceAll xem dấu chấm là literal.
D. `"-"` vì replaceAll chỉ thay match đầu tiên.
Đáp án đúng: A

Câu 26. Với `"abc123".matches("\\d+")`, kết quả là gì?
A. `true` vì regex chỉ cần xuất hiện một đoạn chứa số.
B. `false` vì matches đòi regex khớp toàn bộ chuỗi.
C. `true` vì matches tự bỏ phần chữ cái trước các số.
D. `false` vì \d chỉ khớp một chữ số và không có +.
Đáp án đúng: B

Câu 27. Với `Pattern.compile("\\d+").matcher("a12b").find()`, kết quả là gì?
A. `false` vì find cũng cần khớp hết chuỗi nguồn.
B. `false` vì matcher chỉ khớp ở đầu chuỗi nguồn.
C. `true` vì find khớp đoạn `12` trong chuỗi.
D. `true` vì regex \d+ khớp cả chữ cái a và b.
Đáp án đúng: C

Câu 28. Với `"a,b,".split(",")`, kích thước mảng nhận được là bao nhiêu?
A. `1` vì split trả toàn bộ chuỗi trước dấu phẩy đầu.
B. `3` vì split mặc định giữ cả phần tử rỗng cuối.
C. `4` vì mỗi dấu phẩy tạo thêm hai phần tử rỗng.
D. `2` vì split mặc định loại các chuỗi rỗng ở cuối.
Đáp án đúng: D

Câu 29. Với `"a,b,".split(",", -1)`, kích thước mảng là bao nhiêu?
A. `4` vì limit âm tách thêm phần tử trước dấu đầu.
B. `3` vì limit âm giúp giữ phần tử rỗng ở cuối.
C. `2` vì limit âm vẫn bỏ phần tử rỗng cuối.
D. `1` vì limit âm chỉ trả phần tử đầu tiên.
Đáp án đúng: B

Câu 30. Để tìm một chuỗi do người dùng nhập như văn bản literal trong regex, nên làm gì?
A. Dùng `Pattern.compile(input)` vì mặc định không xử lý regex.
B. Dùng `input.toLowerCase()` để biến regex thành literal.
C. Dùng `Pattern.quote(input)` để thoát các metacharacter.
D. Dùng `input.trim()` để xóa mọi metacharacter của regex.
Đáp án đúng: C

Câu 31. Với `"é".getBytes(StandardCharsets.UTF_8).length`, kết quả nào đúng?
A. `3` vì mọi ký tự có dấu cần ba byte UTF-8.
B. `2` vì U+00E9 được mã hóa thành hai byte UTF-8.
C. `1` vì UTF-8 luôn dùng một byte cho mỗi Java char.
D. `4` vì Java String mặc định dùng UTF-32 khi mã hóa.
Đáp án đúng: B

Câu 32. Hai chuỗi `"é"` và `"e\u0301"` trông giống nhau; cách nào so sánh nội dung chuẩn hơn?
A. Chuẩn hóa Unicode bằng NFC trước khi so bằng equals.
B. Gọi intern lên hai chuỗi vì string pool chuẩn hóa Unicode.
C. Chuyển cả hai sang UTF-8 rồi so số byte của hai chuỗi.
D. Gọi equals trực tiếp vì Java tự chuẩn hóa các dấu kết hợp.
Đáp án đúng: A
