Câu 1: Kiểu nguyên thủy `int` trong Java có biểu diễn nào?
A. 32 bit, là số nguyên có dấu theo bù hai.
B. 32 bit nhưng không mang dấu.
C. 64 bit và có dấu theo bù hai.
D. 16 bit và có dấu theo bù hai.
Đáp án đúng: A

Câu 2: Muốn lưu literal thập phân `3_000_000_000` trong biến `long`, khai báo nào biên dịch?
A. `long n = 3_000_000_000L;`
B. `long n = 3_000_000_000F;`
C. `long n = (long) 3_000_000_000;`
D. `long n = 3_000_000_000;`
Đáp án đúng: A

Câu 3: Nếu `a` và `b` đều là biến `byte`, biểu thức `a + b` có kiểu gì?
A. Kiểu `short` để hạn chế nguy cơ tràn số.
B. Kiểu `int` vì phép cộng thực hiện thăng hạng số nguyên.
C. Kiểu `long` để chứa được mọi tổng byte.
D. Kiểu `byte` vì hai toán hạng đều là byte.
Đáp án đúng: B

Câu 4: Với `short s = 100; s = s + 1;`, điều gì xảy ra khi biên dịch?
A. Biên dịch vì Java tự thu hẹp về `short`.
B. Không biên dịch vì `s + 1` có kiểu `int`.
C. Không biên dịch vì `short` cấm toán tử cộng.
D. Biên dịch vì phép cộng giữ kiểu `short`.
Đáp án đúng: B

Câu 5: Với `short s = 100; s += 1;`, kết quả nào đúng?
A. Biên dịch; `+=` thu hẹp kết quả về `short`.
B. Không biên dịch do `s + 1` luôn là `int`.
C. Ném ngoại lệ vì `short` không được dùng `+=`.
D. Biên dịch nhưng biến `s` đổi thành kiểu `int`.
Đáp án đúng: A

Câu 6: Kết quả của `Integer.MAX_VALUE + 1` khi tính bằng `int` là gì?
A. Trả về giá trị `0` sau khi tràn.
B. Quay vòng thành `Integer.MIN_VALUE`.
C. Giữ ở giá trị `Integer.MAX_VALUE`.
D. Ném `ArithmeticException` khi vượt miền.
Đáp án đúng: B

Câu 7: Điều gì xảy ra khi `Math.addExact(Integer.MAX_VALUE, 1)` được gọi?
A. Trả về `Integer.MIN_VALUE` do quay vòng.
B. Chuyển kết quả lên kiểu `long` tự động.
C. Trả về `Integer.MAX_VALUE` do bão hòa.
D. Ném `ArithmeticException` khi phép cộng tràn.
Đáp án đúng: D

Câu 8: Khi tích của hai biến `long` vượt phạm vi, `Math.multiplyExact` có hành vi nào?
A. Trả về số `long` đã quay vòng như toán tử `*`.
B. Giữ giá trị lớn nhất biểu diễn được của `long`.
C. Tự tạo `BigInteger` để giữ đầy đủ tích.
D. Ném `ArithmeticException` thay vì quay vòng.
Đáp án đúng: D

Câu 9: Giá trị `Math.abs(Integer.MIN_VALUE)` là gì?
A. Ném `ArithmeticException` trong mọi JDK.
B. Vẫn là `Integer.MIN_VALUE` do tràn số.
C. Bằng `Integer.MAX_VALUE` do giới hạn giá trị.
D. Bằng `0` vì trị tuyệt đối gây tràn.
Đáp án đúng: B

Câu 10: Biểu thức Java `7 / 2` với hai literal nguyên cho kết quả nào?
A. Số nguyên `4`, vì phép chia làm tròn gần.
B. Số thực `3.5`, kiểu `double` tự chọn.
C. Số nguyên `3`, phần lẻ của thương bị bỏ.
D. Số thực `3.0`, kiểu kết quả là `double`.
Đáp án đúng: C

Câu 11: Trong Java, `-7 % 3` có kết quả nào?
A. `-1`, phần dư cùng dấu với số bị chia.
B. `2`, phần dư luôn không âm với mọi toán hạng.
C. `-2`, lấy dấu theo số chia là số dương.
D. `1`, lấy trị tuyệt đối của phần dư.
Đáp án đúng: A

Câu 12: `Math.floorDiv(-7, 3)` trả về giá trị nào?
A. `-3`, thương được làm tròn về âm vô cực.
B. `-1`, kết quả chỉ là phần dư có dấu.
C. `2`, thương được đổi thành phần dư dương.
D. `-2`, thương được cắt về phía số không.
Đáp án đúng: A

Câu 13: `Math.floorMod(-7, 3)` trả về giá trị nào?
A. `-2`, là trị âm của phần dư không dấu.
B. `1`, bằng trị tuyệt đối của toán tử `%`.
C. `-1`, giống toán tử phần dư `%` của Java.
D. `2`, theo phép floorMod với số chia dương.
Đáp án đúng: D

Câu 14: Khi ép kiểu `(int) 7.9d`, kết quả nhận được là gì?
A. `7`, do phần thập phân bị cắt về phía không.
B. `8`, do tự làm tròn tới số nguyên gần nhất.
C. Lỗi biên dịch, vì không thể ép `double` sang `int`.
D. `7.9`, vì giữ nguyên phần thập phân của double.
Đáp án đúng: A

Câu 15: Khi ép kiểu `(int) Double.NaN`, kết quả là gì?
A. `0`, theo quy tắc thu hẹp số thực sang nguyên.
B. `Integer.MIN_VALUE`, vì NaN nhỏ hơn mọi số.
C. `Integer.MAX_VALUE`, vì NaN vượt mọi số.
D. Ném `ArithmeticException`, vì NaN không hữu hạn.
Đáp án đúng: A

Câu 16: Khi ép `(int) Double.POSITIVE_INFINITY`, Java cho kết quả nào?
A. `0`, vì giá trị vô cực không có phần nguyên.
B. `Integer.MIN_VALUE`, do tràn vòng số nguyên.
C. `Integer.MAX_VALUE`, vì bị chặn ở biên trên.
D. Ném `ArithmeticException`, vì không chuyển được.
Đáp án đúng: C

Câu 17: Đoạn `long n = 1 << 40;` gán giá trị nào cho `n`?
A. `256`, vì 40 được rút gọn theo khoảng dịch của `int`.
B. `1099511627776`, vì biến đích có kiểu `long`.
C. Lỗi biên dịch, vì khoảng dịch bit vượt 31.
D. `0`, vì dịch quá 31 bit làm mất mọi bit.
Đáp án đúng: A

Câu 18: Đoạn `long n = 1L << 40;` gán giá trị nào cho `n`?
A. `1099511627776`, vì toán hạng trái có kiểu `long`.
B. `256`, vì mọi phép dịch đều được tính bằng `int`.
C. `0`, vì 40 vượt kích thước toán hạng số nguyên.
D. Lỗi biên dịch, vì Java giới hạn số bit dịch ở 31.
Đáp án đúng: A

Câu 19: Khi gọi `Integer.parseInt("2147483648")`, điều gì xảy ra?
A. Trả về `Integer.MIN_VALUE` do tràn vòng.
B. Ném `NumberFormatException` vì vượt miền.
C. Trả về `Integer.MAX_VALUE` do bị giới hạn.
D. Tự trả về `long` vì chuỗi quá phạm vi `int`.
Đáp án đúng: B

Câu 20: `Integer.toUnsignedString(-1)` tạo chuỗi thập phân nào?
A. `2147483647`, vì bỏ bit dấu của số nguyên.
B. `4294967295`, diễn giải số không dấu 32 bit.
C. `-1`, vì vẫn hiển thị giá trị có dấu ban đầu.
D. `0`, vì số âm được quy đổi về không.
Đáp án đúng: B

Câu 21: `Integer.compareUnsigned(-1, 1)` cho kết quả có dấu nào?
A. Âm, vì `-1` nhỏ hơn `1` khi so sánh signed.
B. Ném ngoại lệ, vì không thể so unsigned số âm.
C. Dương, vì `-1` lớn hơn `1` theo unsigned.
D. Bằng không, vì bỏ bit dấu làm hai số bằng nhau.
Đáp án đúng: C

Câu 22: Với `Integer a = 127; Integer b = 127;`, nhận định nào đúng?
A. `a == b` không xác định cả ở phạm vi 127.
B. `a == b` luôn sai vì tạo hai đối tượng mới.
C. `a == b` lỗi biên dịch với hai wrapper.
D. `a == b` đúng theo bảo đảm cache cho 127.
Đáp án đúng: D

Câu 23: Với `Integer a = 1000; Integer b = 1000;`, nên so sánh giá trị thế nào?
A. So `System.identityHashCode(a)` và `System.identityHashCode(b)`.
B. Dùng `a == b`, vì boxing luôn dùng cùng instance.
C. Dùng `a.equals(b)`, không dựa vào identity `==`.
D. Dùng `a.toString() == b.toString()` để so chuỗi.
Đáp án đúng: C

Câu 24: Với `Integer n = null; int x = n;`, điều gì xảy ra khi chạy?
A. Lỗi biên dịch vì không thể dùng wrapper với `int`.
B. Gán `Integer.MIN_VALUE` để biểu thị thiếu dữ liệu.
C. Ném `NullPointerException` khi tự unboxing giá trị `null`.
D. Gán `0` vì wrapper null có giá trị mặc định.
Đáp án đúng: C

Câu 25: Khác biệt chính giữa `Integer.parseInt("42")` và `Integer.valueOf("42")` là gì?
A. Cả hai đều trả `Integer` và tạo instance mới.
B. `parseInt` trả `int`, `valueOf` trả `Integer`.
C. Cả hai đều trả `long` nếu chuỗi là số nguyên.
D. `parseInt` trả `Integer`, còn `valueOf` trả `int`.
Đáp án đúng: B

Câu 26: Miền giá trị của kiểu nguyên thủy `byte` là miền nào?
A. Từ `-32768` đến `32767`, tính hai đầu.
B. Từ `-255` đến `255`, tính cả hai đầu.
C. Từ `0` đến `255`, tính cả hai đầu.
D. Từ `-128` đến `127`, tính cả hai đầu.
Đáp án đúng: D

Câu 27: Kiểu nguyên thủy `char` trong Java lưu giá trị số theo cách nào?
A. Đơn vị mã UTF-16 không dấu, rộng 16 bit.
B. Mã Unicode code point đầy đủ trong 32 bit.
C. Số nguyên có dấu 16 bit cho mọi ký tự.
D. Đơn vị mã UTF-8 thay đổi từ 1 đến 4 byte.
Đáp án đúng: A

Câu 28: Khai báo `float f = 0.1;` có vấn đề gì?
A. Không biên dịch vì `float` chỉ chứa số nguyên.
B. Biên dịch vì `float` tự giữ chính xác literal số thực.
C. Không biên dịch: `0.1` là `double`, cần hậu tố `f`.
D. Biên dịch nhưng `float` tự được nâng thành `double`.
Đáp án đúng: C

Câu 29: Trong Java dùng `double`, biểu thức `0.1 + 0.2 == 0.3` thường có giá trị nào?
A. Lỗi biên dịch, vì không được so sánh hai `double`.
B. `true`, vì toán tử `==` tự làm tròn số trước khi so.
C. `false`, vì phép cộng nhị phân không cho đúng tổng `0.3`.
D. `true`, vì mọi literal thập phân đều lưu chính xác.
Đáp án đúng: C

Câu 30: So sánh `Double.NaN == Double.NaN` trả về gì?
A. `true`, vì NaN được xem là vô cực dương.
B. Ném ngoại lệ, vì toán tử `==` không nhận NaN.
C. `true`, vì hai hằng đều có cùng dạng NaN.
D. `false`, vì NaN không bằng chính nó qua `==`.
Đáp án đúng: D

Câu 31: Cách nhận biết một giá trị `double` là NaN theo API chuẩn là gì?
A. Gọi `Double.isNaN(value)` để kiểm tra.
B. So `value == Double.POSITIVE_INFINITY` để kiểm tra.
C. So `value == Double.NaN` để kiểm tra.
D. So `value > Double.MAX_VALUE` để kiểm tra.
Đáp án đúng: A

Câu 32: Kết quả của phép chia số thực `1.0 / 0.0` trong Java là gì?
A. `0.0`, vì thương được làm tròn về không.
B. `Double.POSITIVE_INFINITY`, không ném ngoại lệ.
C. `ArithmeticException`, vì không thể chia cho không.
D. `Double.NaN`, vì số chia bằng không.
Đáp án đúng: B

Câu 33: Kết quả của biểu thức số thực `0.0 / 0.0` trong Java là gì?
A. `0.0`, vì cả tử và mẫu đều bằng không.
B. `ArithmeticException`, vì đây là chia cho không.
C. `Double.POSITIVE_INFINITY`, vì số chia bằng không.
D. `Double.NaN`, do phép toán không xác định.
Đáp án đúng: D

Câu 34: Với `double a = -0.0, b = +0.0;`, nhận định nào chính xác?
A. `a == b` sai, nhưng `Double.compare(a,b)` dương.
B. `a == b` đúng, và `Double.compare(a,b)` bằng không.
C. `a == b` sai, nhưng `Double.compare(a,b)` bằng không.
D. `a == b` đúng, nhưng `Double.compare(-0.0,+0.0)` âm.
Đáp án đúng: D

Câu 35: `Float.MIN_VALUE` biểu thị điều gì trong Java?
A. Số `float` dương nhỏ nhất lớn hơn không.
B. Số `float` âm nhỏ nhất gần số không nhất.
C. Giá trị chuẩn hóa dương lớn nhất của `float`.
D. Số `float` âm hữu hạn có độ lớn cực đại.
Đáp án đúng: A

Câu 36: Kết quả của `Math.round(-2.5d)` là gì?
A. `-1L`, vì bỏ dấu âm trước khi làm tròn.
B. `-2L`, vì quy tắc làm tròn về `floor(x + 0.5)`.
C. `-3L`, vì luôn làm tròn xa số không tại điểm giữa.
D. `-2.5d`, vì giữ nguyên kiểu và giá trị đầu vào.
Đáp án đúng: B

Câu 37: `Math.floor(-1.2d)` trả về giá trị nào?
A. `-3.0`, vì luôn lùi hai đơn vị trên số âm.
B. `-1.2`, vì không đổi giá trị số thực đầu vào.
C. `-1.0`, số nguyên gần nhất không nhỏ hơn đầu vào.
D. `-2.0`, do floor làm tròn về âm vô cực.
Đáp án đúng: D

Câu 38: `Math.ceil(-1.2d)` trả về giá trị nào?
A. `-2.0`, số nguyên gần nhất không lớn hơn đầu vào.
B. `-1.2`, vì không đổi giá trị số thực đầu vào.
C. `-1.0`, do ceil làm tròn về dương vô cực.
D. `0.0`, vì số âm được làm tròn về số không.
Đáp án đúng: C

Câu 39: `Double.isFinite(Double.POSITIVE_INFINITY)` trả về gì?
A. `true`, vì không phải giá trị `Double.NaN`.
B. `false`, vì vô cực không phải số hữu hạn.
C. `true`, vì vô cực là một giá trị `double`.
D. Lỗi runtime, vì isFinite không nhận số vô cực.
Đáp án đúng: B

Câu 40: Khi gọi `Math.toIntExact(Long.MAX_VALUE)`, điều gì xảy ra?
A. Trả về `long` nguyên vẹn để tránh mất dữ liệu.
B. Ném `ArithmeticException` vì vượt phạm vi `int`.
C. Quay vòng thành `-1` như phép ép kiểu xuống `int`.
D. Trả `Integer.MAX_VALUE` do giới hạn đầu ra.
Đáp án đúng: B

Câu 41: Điều gì khác nhau giữa `new BigDecimal(0.1)` và `new BigDecimal("0.1")`?
A. Bản nhận `double` giữ xấp xỉ nhị phân chính xác.
B. Bản nhận chuỗi chuyển qua `float` trước khi lưu.
C. Hai cách luôn tạo cùng giá trị thập phân 0.1.
D. Bản nhận `double` tự động làm tròn hai chữ số.
Đáp án đúng: A

Câu 42: `BigDecimal.valueOf(0.1d)` có đặc điểm nào so với `new BigDecimal(0.1d)`?
A. Trả về một `double` chứ không phải `BigDecimal`.
B. Luôn có cùng scale và unscaled value như constructor.
C. Tạo `BigDecimal` chứa đúng `0.1` qua chuỗi của `double`.
D. Tự làm tròn về hai chữ số thập phân của giá trị.
Đáp án đúng: C

Câu 43: Gọi `a.add(b)` với hai đối tượng `BigDecimal` có làm đổi `a` không?
A. Không; lời gọi chỉ có tác dụng khi `b` bằng không.
B. Không; phép cộng trả về một `BigDecimal` mới.
C. Có; cả hai đối tượng đều được cập nhật giá trị.
D. Có; đối tượng `a` được thay đổi trực tiếp.
Đáp án đúng: B

Câu 44: Với `new BigDecimal("2.0")` và `new BigDecimal("2.00")`, `equals` trả về gì?
A. Ném ngoại lệ, vì hai số có scale khác nhau.
B. `false`, vì `equals` xét cả giá trị và scale.
C. `true`, vì hai đối tượng đều ở kiểu BigDecimal.
D. `true`, vì `equals` chỉ xét độ lớn số học.
Đáp án đúng: B

Câu 45: Với hai `BigDecimal` lần lượt là `2.0` và `2.00`, `compareTo` trả về gì?
A. `0`, vì hai số bằng nhau về số học dù scale khác nhau.
B. Ném ngoại lệ, vì không thể so scale khác nhau.
C. `-1`, vì số đầu có ít chữ số thập phân.
D. `1`, vì scale đầu nhỏ hơn scale thứ hai.
Đáp án đúng: A

Câu 46: Khi chia `BigDecimal.ONE` cho `new BigDecimal("3")` bằng `divide` một tham số, điều gì xảy ra?
A. Trả về `0.33` vì mặc định làm tròn hai chữ số.
B. Trả về `0` vì chia số nguyên trước khi chuyển kiểu.
C. Ném `ArithmeticException` vì thương vô hạn.
D. Trả về `0.3333333333333333` theo chuẩn double.
Đáp án đúng: C

Câu 47: Kết quả `new BigDecimal("2.345").setScale(2, RoundingMode.HALF_UP)` là gì?
A. `2.36`, vì luôn tăng thêm hai đơn vị cuối.
B. `2.34`, vì luôn bỏ phần sau scale.
C. `2.345`, vì setScale không thay đổi giá trị.
D. `2.35`, vì chữ số tiếp theo là năm.
Đáp án đúng: D

Câu 48: Kết quả `new BigDecimal("2.345").setScale(2, RoundingMode.HALF_EVEN)` là gì?
A. `2.345`, vì HALF_EVEN không làm tròn số.
B. `2.36`, vì chuyển tới số chẵn kế tiếp.
C. `2.34`, vì tại điểm giữa HALF_EVEN giữ chữ số cuối chẵn.
D. `2.35`, vì mọi điểm giữa đều làm tròn lên.
Đáp án đúng: C

Câu 49: Với `new BigDecimal("123.45")`, cặp unscaled value và scale là gì?
A. `123` và `2`, vì phần thập phân bị loại bỏ.
B. `12345` và `5`, vì có năm chữ số có nghĩa.
C. `12345` và `0`, vì số đã được chuẩn hóa.
D. `12345` và `2`, theo biểu diễn thập phân.
Đáp án đúng: D

Câu 50: Điểm chính của `BigDecimal.toPlainString()` là gì?
A. Chuyển số về chuỗi nhị phân đúng theo IEEE 754.
B. Đổi mọi giá trị về hai chữ số thập phân cố định.
C. Thay toàn bộ chữ số không có nghĩa bằng dấu cách.
D. Hiển thị số thập phân không dùng ký pháp số mũ.
Đáp án đúng: D

Câu 51: Khi gọi `new BigDecimal("1000").stripTrailingZeros()`, điều nào có thể xảy ra?
A. Ném ngoại lệ vì không thể bỏ số không ở cuối.
B. Giá trị số học bị đổi từ 1000 thành 1.
C. Scale có thể âm và chuỗi có thể dùng số mũ.
D. Scale giữ bằng không trong mọi trường hợp.
Đáp án đúng: C

Câu 52: `MathContext.DECIMAL64` kiểm soát điều gì trong phép tính BigDecimal?
A. Precision 16 chữ số có nghĩa và làm tròn.
B. Phạm vi tối đa 64 bit cho mọi BigDecimal.
C. Tự chuyển mọi phép toán sang kiểu double.
D. Scale cố định 16 chữ số sau dấu thập phân.
Đáp án đúng: A

Câu 53: `new BigDecimal("12.5").intValueExact()` có hành vi nào?
A. Trả `12`, vì phép đổi số nguyên tự cắt phần lẻ.
B. Trả `13`, vì tự làm tròn đến số nguyên gần nhất.
C. Trả `12.5`, nhưng đóng gói trong đối tượng Integer.
D. Ném `ArithmeticException` vì có phần thập phân.
Đáp án đúng: D

Câu 54: Kết quả `new BigDecimal("5").divide(new BigDecimal("2"), 2, RoundingMode.HALF_UP)` là gì?
A. `2.5`, vì mọi số không cuối đều được lược bỏ.
B. `2.00`, vì phép chia được thực hiện trên số nguyên.
C. `3.00`, vì mọi phép chia đều được làm tròn lên.
D. `2.50`, vì thương được biểu diễn với scale 2.
Đáp án đúng: D

Câu 55: `new BigInteger("FF", 16)` biểu thị giá trị thập phân nào?
A. `1515`, vì hai chữ số F được ghép thành số.
B. `255`, vì `FF` được đọc theo cơ số mười sáu.
C. `16`, vì `F` là chữ số lớn nhất của cơ số.
D. Ném lỗi, vì BigInteger chỉ nhận chuỗi thập phân.
Đáp án đúng: B

Câu 56: Gọi `a.add(b)` với `BigInteger` có thay đổi đối tượng `a` không?
A. Có; đối tượng `b` cũng tăng theo giá trị `a`.
B. Có; `BigInteger` tự sửa vùng nhớ của `a`.
C. Không; `BigInteger.add` trả về số mới.
D. Không; phép cộng luôn trả về cùng đối tượng `a`.
Đáp án đúng: C

Câu 57: `BigInteger.valueOf(-7).mod(BigInteger.valueOf(3))` có kết quả gì?
A. Ném lỗi, vì toán hạng bên trái âm.
B. `-1`, vì phép mod giống toán tử `%` số nguyên.
C. `2`, vì môđun dương cho phần dư không âm.
D. `1`, vì lấy trị tuyệt đối của phần dư.
Đáp án đúng: C

Câu 58: `BigInteger.valueOf(-7).remainder(BigInteger.valueOf(3))` trả về gì?
A. `2`, vì remainder luôn đưa về số không âm.
B. `1`, vì tự đổi dấu phần dư khi có số âm.
C. Ném lỗi, vì remainder không nhận số âm.
D. `-1`, vì remainder giữ dấu của số bị chia âm.
Đáp án đúng: D

Câu 59: `BigInteger.TEN.pow(-1)` có hành vi nào?
A. Ném `NumberFormatException` vì số mũ không hợp lệ.
B. Trả về `0`, do chia nguyên sau khi lấy nghịch đảo.
C. Trả về `0.1` dưới dạng đối tượng BigInteger.
D. Ném `ArithmeticException` vì số mũ nguyên âm.
Đáp án đúng: D

Câu 60: Khi dịch trái một `BigInteger` 1000 bit, nhận định nào đúng?
A. Kết quả tự trở thành một đối tượng BigDecimal.
B. Giá trị luôn bị cắt về 64 bit như kiểu long.
C. Không bị giới hạn 32 hay 64 bit như `int`/`long`.
D. Phép dịch ném lỗi khi khoảng dịch vượt 63 bit.
Đáp án đúng: C

Câu 61: `BigInteger.valueOf(48).gcd(BigInteger.valueOf(18))` trả về gì?
A. `864`, tích của hai đối số đầu vào.
B. `6`, ước chung lớn nhất của hai số.
C. `66`, tổng của hai đối số đầu vào.
D. `3`, ước chung nguyên tố nhỏ nhất của hai số.
Đáp án đúng: B

Câu 62: `BigInteger.valueOf(-7).divide(BigInteger.valueOf(3))` trả về gì?
A. `-1`, vì trả về phần dư của phép chia.
B. `-3`, phép chia nguyên lấy sàn về âm vô cực.
C. `-2`, do thương bị cắt về phía số không.
D. `2`, vì đối tượng BigInteger chỉ lưu độ lớn.
Đáp án đúng: C

Câu 63: Kết quả của phép dịch phải không dấu `-1 >>> 1` với kiểu `int` là gì?
A. `0`, vì số âm bị đổi thành giá trị không.
B. `2147483647`, vì phép dịch điền bit không ở bên trái.
C. `-1`, vì phép dịch phải luôn giữ bit dấu.
D. `-2147483648`, vì bit dấu được đảo lại.
Đáp án đúng: B

Câu 64: Ứng dụng tính số tiền theo thập phân với yêu cầu làm tròn công khai nên ưu tiên cách nào?
A. Dùng BigDecimal từ chuỗi, làm tròn tường minh.
B. Dùng int cho mọi giao dịch mà không xét đơn vị.
C. Dùng float vì biểu diễn gọn hơn double trong heap.
D. Dùng double và so sánh trực tiếp sau mỗi phép tính.
Đáp án đúng: A
