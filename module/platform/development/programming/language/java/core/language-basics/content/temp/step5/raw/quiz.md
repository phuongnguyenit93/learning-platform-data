Câu 1. Với tệp `App.java` chứa `public class App`, lệnh JDK nào biên dịch mã nguồn thành bytecode?
A. Dùng `java App.java` để xuất class file bằng compiler.
B. Dùng `javadoc App.java` để sinh bytecode thực thi.
C. Dùng `javac App.java` để tạo class file từ mã nguồn.
D. Dùng `jar App.java` để sinh bytecode cho class App.
Đáp án đúng: C

Câu 2. Khi đã biên dịch `App.java` ra `App.class`, lệnh thông thường nào chạy lớp chứa `main`?
A. Dùng `jar App.class` để JVM gọi phương thức main.
B. Dùng `java App.class` để JVM chạy từ tên tệp class.
C. Dùng `javac App` để trình biên dịch gọi entry point.
D. Dùng `java App` để JVM tìm và thực thi entry point.
Đáp án đúng: D

Câu 3. Với chương trình class Java thông thường trên JDK 17, khai báo entry point nào phù hợp?
A. `private static void main(String[] args)` là entry point chuẩn.
B. `public static void main(String[] args)` là entry point hợp lệ.
C. `public void main(String[] args)` là entry point tiêu chuẩn.
D. `protected static int main(String[] args)` là entry point chuẩn.
Đáp án đúng: B

Câu 4. Trong các kiểu sau, kiểu nào là primitive type của Java?
A. `int` là primitive type lưu số nguyên 32-bit.
B. `int[]` là primitive vì chứa các giá trị int.
C. `Integer` là primitive vì bao bọc số nguyên.
D. `String` là primitive vì hỗ trợ chuỗi ký tự.
Đáp án đúng: A

Câu 5. Khi viết `int n; System.out.println(n);` trong cùng một method, điều gì xảy ra?
A. Lỗi biên dịch do biến local `n` chưa được gán.
B. Chạy in `null` vì n chưa được khởi tạo.
C. JVM cấp giá trị ngẫu nhiên lúc chạy rồi in ra.
D. Chạy in `0` do mặc định của biến local kiểu int.
Đáp án đúng: A

Câu 6. Khi tạo `new Customer()` và class có instance field `boolean active;`, giá trị ban đầu của field là gì?
A. Giá trị `null` vì boolean chưa được gán tường minh.
B. Giá trị `true` vì object đã khởi tạo thành công.
C. Compiler lỗi vì mọi instance field phải có initializer.
D. Giá trị `false` được gán mặc định cho boolean field.
Đáp án đúng: D

Câu 7. Biểu thức Java `7 / 2` cho kết quả nào khi cả hai operand đều là `int`?
A. Giá trị `3` vì phép chia số nguyên loại phần dư.
B. Giá trị `4` vì kết quả được làm tròn tới số gần.
C. Giá trị `3.5` vì compiler tự chuyển sang double.
D. Giá trị `2` vì phép chia trả phần dư của 7 cho 2.
Đáp án đúng: A

Câu 8. Lệnh gán nào hợp lệ mà không cần explicit cast trong Java?
A. `int x = true;` là phép chuyển boolean sang int.
B. `long x = 12;` hợp lệ vì int được widening thành long.
C. `long x = 2.5;` là phép chuyển hẹp double sang long.
D. `int x = 12L;` là phép chuyển hẹp long sang int.
Đáp án đúng: B

Câu 9. Với `int x = 0;`, biểu thức `x != 0 && 10 / x > 1` được đánh giá thế nào?
A. Cho `true` vì nhánh phải bị bỏ qua khi nhánh trái sai.
B. Ném `ArithmeticException` vì phép chia luôn được tính.
C. Cho `false` mà không chia cho zero nhờ short-circuit.
D. Không compile vì `&&` chỉ nhận hằng số boolean.
Đáp án đúng: C

Câu 10. Sau hai lệnh `int n = 4; int r = n++;`, cặp giá trị `r` và `n` là gì?
A. `r = 4`, `n = 4` vì tăng sau khi in.
B. `r = 5`, `n = 5` vì tăng trước khi gán.
C. `r = 4`, `n = 5` vì dùng hậu tố `n++`.
D. `r = 5`, `n = 4` do giữ nguyên biến.
Đáp án đúng: C

Câu 11. Một chương trình dùng `if (x > 0)` với `x` là `int`; yêu cầu nào đúng cho điều kiện `if`?
A. Điều kiện phải là biểu thức boolean, như `x > 0`.
B. Điều kiện cần là `String` chứa `true` hoặc `false`.
C. Điều kiện có thể là số nguyên với `0` là false.
D. Điều kiện cần là biểu thức trả về `int` khác zero.
Đáp án đúng: A

Câu 12. Trong `switch` statement kiểu truyền thống, lệnh `break` ở cuối `case` có tác dụng gì?
A. Thoát toàn bộ phương thức đang chứa switch.
B. Ngăn fall-through và thoát khỏi `switch`.
C. Buộc switch phải trả ra giá trị từ nhánh hiện tại.
D. Chuyển điều khiển tới nhánh `default` ngay sau đó.
Đáp án đúng: B

Câu 13. Vòng `for (int i=0; i<3; i++)` thực thi phần thân bao nhiêu lần nếu không bị ngắt?
A. Ba lần ứng với `i` nhận các giá trị `0, 1, 2`.
B. Một lần vì điều kiện vòng lặp chỉ được kiểm tra đầu.
C. Bốn lần ứng với `i` nhận các giá trị `0, 1, 2, 3`.
D. Hai lần ứng với `i` nhận các giá trị `1, 2`.
Đáp án đúng: A

Câu 14. Trong một vòng lặp Java, `continue` không có nhãn thường thực hiện điều gì?
A. Thoát khỏi vòng lặp và chạy câu lệnh phía sau.
B. Thoát khỏi method hiện tại và trả giá trị mặc định.
C. Bỏ qua phần còn lại của lượt lặp hiện tại.
D. Chạy lại toàn bộ method từ đầu cho lượt kế tiếp.
Đáp án đúng: C

Câu 15. Điểm khác biệt cơ bản của `do { ... } while (condition);` so với `while` là gì?
A. Thân chạy hai lần trước khi kiểm tra điều kiện đầu.
B. Thân chạy trước khi `do-while` kiểm tra điều kiện lần đầu.
C. Thân phải chứa `break` để dừng vòng lặp.
D. Thân chỉ chạy khi điều kiện ban đầu đúng.
Đáp án đúng: B

Câu 16. Với `int[] a = new int[3];`, biểu thức `a.length` có giá trị nào?
A. `3` vì mảng vừa cấp phát có ba phần tử.
B. `0` vì mảng chưa được gán các phần tử.
C. `4` vì Java dự trữ thêm phần tử đầu.
D. `2` vì index cuối cùng hợp lệ là số hai.
Đáp án đúng: A

Câu 17. Với `String[] names = new String[2];`, giá trị của `names[0]` ban đầu là gì?
A. Compiler lỗi vì mảng String cần hai giá trị khởi tạo.
B. `""` vì String trong mảng được tự tạo chuỗi rỗng.
C. `null` là giá trị mặc định của phần tử tham chiếu.
D. `"null"` vì Java tạo chuỗi chứa chữ null.
Đáp án đúng: C

Câu 18. Với `int[] a = {5, 6};`, truy cập `a[2]` khi chạy dẫn đến điều gì?
A. Ném `NullPointerException` vì a thiếu phần tử thứ ba.
B. Trả về `6` vì Java tự giới hạn index lớn nhất.
C. Trả về `0` do phần tử chưa có được mặc định int.
D. Ném `ArrayIndexOutOfBoundsException` vì index 2 ngoài mảng.
Đáp án đúng: D

Câu 19. Với `int[] a={1,2}; for (int x : a) { x++; }`, giá trị `a[0]` sau vòng lặp là gì?
A. Thành `3` vì cả hai lượt đều thay đổi a[0].
B. Thành `0` do vòng for-each gán lại biến đầu.
C. Vẫn là `1` vì `x` nhận bản sao của mỗi int.
D. Thành `2` vì x tăng trực tiếp phần tử mảng.
Đáp án đúng: C

Câu 20. Cặp khai báo nào là method overload hợp lệ trong cùng một class?
A. `void log(int x)` và `static void log(int x)` khác static.
B. `log(int)` và `log(String)` khác kiểu tham số.
C. `int log(int x)` và `long log(int x)` khác kiểu trả về.
D. `void log(int x)` và `void log(int y)` khác tên tham số.
Đáp án đúng: B

Câu 21. Với `void update(StringBuilder b) { b.append("!"); b = new StringBuilder("X"); }` và `StringBuilder s=new StringBuilder("A"); update(s);`, giá trị s là gì?
A. `"A"` vì tham số Java là pass-by-reference cách ly object.
B. `"A!"` vì append sửa object, gán lại b không đổi s.
C. `"A!X"` vì hai object được tự nối khi method trả về.
D. `"X"` vì phép gán lại tham số thay reference của caller.
Đáp án đúng: B

Câu 22. Trong Java, muốn gọi phương thức static `abs` của `Math` để lấy trị tuyệt đối của -5, cú pháp nào phù hợp?
A. `Math->abs(-5)` trả về giá trị `5`.
B. `new Math().abs(-5)` trả về giá trị `5`.
C. `Math.abs(-5)` trả về giá trị `5` kiểu int.
D. `Math::abs(-5)` trực tiếp gọi và trả về `5`.
Đáp án đúng: C

Câu 23. Với `String s = "Hi"; s.concat("!");`, nội dung của s sau lời gọi là gì?
A. Thành `"!"` vì concat thay toàn bộ nội dung.
B. Thành `null` vì kết quả String không được dùng.
C. Vẫn là `"Hi"` vì kết quả concat không được gán lại.
D. Thành `"Hi!"` vì concat sửa object hiện tại.
Đáp án đúng: C

Câu 24. Với `String a = new String("cat"); String b = "cat";`, kết quả nào đúng?
A. `a.equals(b)` true và `a == b` true vì JVM gộp object.
B. `a.equals(b)` false và `a == b` false vì khác cách tạo.
C. `a.equals(b)` false còn `a == b` true vì intern.
D. `a.equals(b)` true còn `a == b` false vì khác object.
Đáp án đúng: D

Câu 25. Vì sao `StringBuilder` hữu ích khi ghép nhiều đoạn chuỗi trong một vòng lặp?
A. Builder chuyển chuỗi thành char array trên native stack.
B. Builder là String immutable nên append được cache.
C. Builder tự đồng bộ thread và bỏ qua nối trong vòng.
D. `append` cập nhật builder thay vì nối String mới mỗi lượt.
Đáp án đúng: D

Câu 26. Với `String s = "Java"`, biểu thức `s.charAt(0)` trả về giá trị nào?
A. Chuỗi `"J"` vì `charAt` trả về đối tượng String.
B. Ký tự `'J'` vì index đầu tiên bằng `0`.
C. Giá trị `0` vì charAt trả về vị trí đầu chuỗi.
D. Ký tự `'a'` vì index đầu tiên bằng `1`.
Đáp án đúng: B

Câu 27. Trong tệp Java khai báo `package demo.app;`, vị trí của package declaration thường ở đâu?
A. Đặt sau các import để compiler xác định classpath trước.
B. Đặt trong method `main` trước khi sử dụng class khác.
C. Đặt bên trong thân `public class App` để chọn package.
D. Trước các import và khai báo type, sau comment nếu có.
Đáp án đúng: D

Câu 28. Với `public class Account` là top-level class, tên tệp nguồn Java cần là gì?
A. `Account.class` vì khai báo class là file bytecode.
B. `PublicAccount.java` vì public class cần tiền tố public.
C. `account.java` vì tên tệp không phân biệt hoa thường.
D. `Account.java` để khớp tên public top-level class.
Đáp án đúng: D

Câu 29. Trong class `Counter`, constructor `Counter(int n) { count = n; }` chủ yếu phục vụ việc gì?
A. Khởi tạo state của object Counter khi tạo instance.
B. Khởi tạo code static của JVM trước khi nạp class.
C. Trả ra một int cho biểu thức gọi constructor.
D. Ghi đè phương thức `main` trong mọi instance Counter.
Đáp án đúng: A

Câu 30. Với `Integer.parseInt("abc")`, ngoại lệ cụ thể nào được ném khi chạy?
A. `NumberFormatException` vì `"abc"` không parse được thành int.
B. `ArrayIndexOutOfBoundsException` vì chuỗi không có số.
C. `IOException` vì chuỗi chưa được đọc từ file văn bản.
D. `ClassCastException` vì String không phải là Integer.
Đáp án đúng: A

Câu 31. Khi dùng `try (BufferedReader r = Files.newBufferedReader(path)) { ... }`, lợi ích chính là gì?
A. Resource được mở lại sau khi khối try kết thúc bình thường.
B. Resource được đóng sau khối try theo quy tắc AutoCloseable.
C. Resource chỉ đóng khi có lỗi trong khối try đang chạy.
D. Resource không cần xử lý IOException trong thao tác đọc file.
Đáp án đúng: B

Câu 32. Khi gọi `Files.readString(Path.of("note.txt"))`, checked exception nào cần xử lý hoặc khai báo?
A. `ClassCastException` khi Path không chuyển thành String.
B. `ArithmeticException` khi file không chia hết kích thước.
C. `NumberFormatException` cho đường dẫn không chứa số.
D. `IOException` cho những lỗi liên quan việc đọc file.
Đáp án đúng: D
