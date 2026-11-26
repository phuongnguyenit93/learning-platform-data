Câu 1. Cho `Object value = "java";`, điều kiện nào khai báo đúng biến pattern `s` kiểu String?
A. Dùng `value instanceof String(s)` để tạo biến s sau phép kiểm tra.
B. Dùng `value instanceof String s` để kiểm tra và ràng buộc biến s.
C. Dùng `value instanceof s String` để khai báo biến s theo kiểu.
D. Dùng `value instanceof String as s` để đặt tên biến được ép kiểu.
Đáp án đúng: B

Câu 2. Trong `if (obj instanceof String s && s.length() > 3)`, vì sao có thể gọi `s.length()`?
A. Biến s được khai báo ở cấp method, không phụ thuộc điều kiện bên trái.
B. Vế phải của `&&` tạo biến s mới trước khi kiểm tra pattern bên trái.
C. Vế phải của `&&` chạy khi pattern bên trái match và s đã có scope.
D. Toán tử `&&` chuyển mọi giá trị obj thành String trước khi gọi method.
Đáp án đúng: C

Câu 3. Vì sao `if (obj instanceof String s || s.isEmpty())` không biên dịch như mong đợi?
A. Biến s luôn có scope ở nhánh phải nhưng chưa thể gọi isEmpty.
B. Phép `instanceof` không thể xuất hiện trong biểu thức có toán tử `||`.
C. Biến s không được bảo đảm có scope ở nhánh phải của `||`.
D. Toán tử `||` yêu cầu hai biểu thức là cùng một type pattern.
Đáp án đúng: C

Câu 4. Sau `if (!(obj instanceof String s)) return;`, điều gì đúng về `s` ở câu lệnh kế tiếp?
A. Biến s sử dụng được vì nhánh không match đã thoát khỏi method.
B. Biến s không sử dụng được do phạm vi bị giới hạn trong if block.
C. Biến s sử dụng được nhưng kiểu của nó ở đây vẫn là Object.
D. Biến s tự động nhận null nếu phép kiểm tra ban đầu thất bại.
Đáp án đúng: A

Câu 5. Khi `obj == null`, biểu thức `obj instanceof String s` có kết quả gì?
A. Ném `NullPointerException` trước khi kiểm tra kiểu String.
B. Trả `true` và binding s thành một String mang giá trị null.
C. Trả `true` khi s được khai báo trong cùng biểu thức instanceof.
D. Trả `false` và không thực hiện binding s cho giá trị null.
Đáp án đúng: D

Câu 6. Sau `if (obj instanceof String s) { use(s); }`, nhận định nào đúng về biến `s`?
A. s giữ kiểu tĩnh Object trong nhánh kiểm tra thành công.
B. s tự động có kiểu CharSequence khi rời khỏi if block.
C. s được khai báo thành field và tồn tại suốt vòng đời object.
D. s có kiểu tĩnh String trong nhánh kiểm tra thành công.
Đáp án đúng: D

Câu 7. Với `if (obj instanceof String s) { ... }` không có return/throw, câu `System.out.println(s)` ngay sau if sẽ thế nào?
A. Biên dịch vì compiler mở rộng s thành biến cục bộ cho cả method.
B. Không biên dịch vì s chưa chắc được gán ở đường đi sau if.
C. Biên dịch vì s được tự động khởi tạo bằng null khi không match.
D. Không biên dịch vì println không hỗ trợ giá trị kiểu String.
Đáp án đúng: B

Câu 8. Biến pattern `s` của `if (obj instanceof String s) { ... } else { ... }` có thể được dùng ở đâu?
A. Trong cả hai nhánh, vì compiler cung cấp s sau khi kiểm tra.
B. Trong nhánh else khi pattern sai, không có s ở nhánh if.
C. Trong biểu thức if và sau toàn bộ if, bất kể pattern có match.
D. s dùng được trong if khi pattern match, không dùng ở else.
Đáp án đúng: D

Câu 9. Từ Java 21, cú pháp pattern switch nào dùng được khi selector có kiểu `Object`?
A. `case String(s) -> s.length();` với biến pattern s kiểu String.
B. `case String as s -> s.length();` trong switch expression.
C. `case instanceof String s -> s.length();` trong switch expression.
D. `case String s -> s.length();` với biến pattern s kiểu String.
Đáp án đúng: D

Câu 10. Trong pattern switch Java 21, cú pháp guard nào phù hợp?
A. `case String s if s.length() > 3 -> ...` dùng từ khóa if.
B. `case String s where s.length() > 3 -> ...` dùng where.
C. `case String s when s.length()>3 -> ...` là cú pháp đúng.
D. `case String s && s.length() > 3 -> ...` dùng toán tử &&.
Đáp án đúng: C

Câu 11. Với `case String s when s.isEmpty() ->`, guard được kiểm tra khi nào?
A. Trước khi selector được kiểm tra có phải String hay không.
B. Sau khi giá trị match String và s được bind từ selector.
C. Mỗi khi một case trước đó có kiểu khác bị bỏ qua.
D. Ngay khi biên dịch, dựa trên độ dài mặc định của String.
Đáp án đúng: B

Câu 12. Khi `case String s when s.isEmpty()` có type match nhưng guard false, switch tiếp tục ra sao?
A. Switch xét case kế tiếp khi guard trả false.
B. Chạy case vừa match kiểu dù guard false.
C. Bỏ qua các case còn lại và trả về giá trị null mặc định.
D. Ném ClassCastException do String có độ dài khác không.
Đáp án đúng: A

Câu 13. Vì sao đặt `case CharSequence c ->` trước `case String s ->` trong cùng switch Object gây lỗi?
A. String bị dominance vì là subtype của CharSequence.
B. Case CharSequence bị dominance vì nó rộng hơn String.
C. Lỗi do String không implement interface CharSequence.
D. Hai case hợp lệ; JVM chọn nhánh xuất hiện sau.
Đáp án đúng: A

Câu 14. Với `switch (obj)` kiểu Object, thứ tự case nào tránh dominance giữa String và CharSequence?
A. Đặt hai case cùng nhãn để compiler tự quyết định precedence.
B. Đặt `case CharSequence c` trước rồi đến `case String s`.
C. Đặt `case String s` trước rồi đến `case CharSequence c`.
D. Đặt case String phía sau default để tránh kiểm tra trùng.
Đáp án đúng: C

Câu 15. Hai case `case String s when s.isBlank()` rồi `case String s` trong switch Object có hợp lệ không?
A. Hợp lệ vì case có guard đứng trước case String tổng quát.
B. Không hợp lệ vì case có guard luôn lấn át case không guard.
C. Không hợp lệ vì không thể khai báo lại tên s ở case sau.
D. Hợp lệ nhưng JVM sẽ bỏ qua guard khi String không rỗng.
Đáp án đúng: A

Câu 16. Với `switch (obj)` trong Java 21, `case null ->` có tác dụng chính nào?
A. Xử lý riêng giá trị selector null thay vì để switch ném lỗi.
B. Chuyển selector null thành instance của kiểu pattern kế tiếp.
C. Cho phép null match mọi `case String s` trong cùng switch.
D. Loại bỏ yêu cầu khai báo default khi switch có kiểu Object.
Đáp án đúng: A

Câu 17. Nếu pattern switch có `default -> ...` nhưng không có `case null`, selector null thường gây gì?
A. Chạy default vì null không khớp các case kia.
B. Ném `NullPointerException`, không chạy default.
C. Chọn ngẫu nhiên một case nếu các guard đều trả false.
D. Chạy case đầu tiên có type pattern tham chiếu phù hợp.
Đáp án đúng: B

Câu 18. Trong Java 21, nhãn nào hợp lệ để xử lý cả null lẫn trường hợp còn lại?
A. `case null || default -> ...` dùng phép OR trong label.
B. `case null: default -> ...` kết hợp các label.
C. `case default, null -> ...` là thứ tự nhãn được yêu cầu.
D. `case null, default -> ...` xử lý null và còn lại.
Đáp án đúng: D

Câu 19. Với switch expression trên `Object` có case String, Integer và không có default hay case bao quát, điều gì xảy ra?
A. Không biên dịch vì switch chưa bao phủ các Object khác.
B. Không biên dịch vì switch expression thiếu case null.
C. Biên dịch và trả null nếu đối tượng không thuộc hai kiểu đã nêu.
D. Biên dịch và bỏ qua switch expression khi không có case match.
Đáp án đúng: A

Câu 20. Sealed interface `Expr permits Num, Add` với Num và Add final; switch Expr có hai case Num và Add, điều gì đúng?
A. Không hợp lệ vì Expr là sealed interface.
B. Có thể không cần default vì hai subtype đều được xét.
C. Switch expression vẫn cần default vì interface không là enum.
D. Switch expression cần thêm case Expr để nhận giá trị null.
Đáp án đúng: B

Câu 21. Với sealed `Expr permits Num, Add`, trong đó Add là `non-sealed class`; case `Add a` bao phủ đối tượng nào?
A. Chỉ bao phủ subtype final của Add, không bao phủ bản thân Add.
B. Chỉ bao phủ instance Add trực tiếp, không bao phủ subclass.
C. Không bao phủ Add nếu nhánh Num đã được kiểm tra trước.
D. Bao phủ Add và các subtype của Add hợp lệ tại runtime.
Đáp án đúng: D

Câu 22. Điều nào cần lưu ý về case `default` trong switch expression exhaustive trên sealed type?
A. Default trả null khi subtype mới không match case nào.
B. Default biến type pattern trong switch thành unchecked cast.
C. Default buộc compiler kiểm tra thêm mọi subtype mới trước khi chạy.
D. Default có thể che lỗi khi sealed type thêm subtype mới.
Đáp án đúng: D

Câu 23. Với `switch` expression dùng `case String s -> s.length();`, biểu thức `s.length()` có vai trò gì?
A. Giá trị của nhánh được dùng làm kết quả switch expression.
B. Giá trị của nhánh phải được trả bằng `yield` ngay sau mũi tên.
C. Nhánh luôn chuyển tiếp sang case kế để tính giá trị cuối.
D. Phương thức chỉ được gọi để lấy side effect rồi trả null.
Đáp án đúng: A

Câu 24. Trong switch rule dùng cú pháp `case T t ->`, tác động nào đúng so với switch statement kiểu colon?
A. Rule arrow làm mất khả năng dùng case null và when guard.
B. Arrow cần break để không chạy sang case kế tiếp.
C. Rule arrow chạy tất cả các case type match cùng selector.
D. Rule arrow không fall-through sang nhánh kế tiếp.
Đáp án đúng: D

Câu 25. Với `record Point(int x, int y) {}` và selector kiểu Object, case nào bóc tách đúng hai thành phần?
A. `case Point(x, y) -> ...` tự tạo hai biến pattern không kiểu.
B. `case Point{int x, int y} -> ...` dùng cú pháp record pattern.
C. `case Point(int x, int y) -> ...` là record pattern hợp lệ.
D. `case Point[x, y] -> ...` đọc hai field bằng cú pháp array.
Đáp án đúng: C

Câu 26. Với `record Point(int x, int y) {}`, cách kiểm tra và bóc tách trong biểu thức if nào hợp lệ trên Java 21?
A. `if (obj instanceof Point[int x, int y])` bind record.
B. `if (obj instanceof Point(int x, int y))` hợp lệ.
C. `if (obj instanceof Point(x, y))` tự bind biến.
D. `if (obj instanceof Point{int x, int y})` bind record.
Đáp án đúng: B

Câu 27. Với `record Line(Point from, Point to) {}` và `record Point(int x,int y) {}`, record pattern lồng nhau nào đúng?
A. `Line(Point(var x, var y), Point(var a, var b))` hợp lệ.
B. `Line{Point(x, y), Point(a, b)}` là cú pháp deconstruction.
C. `Line(Point.from(x, y), Point.to(a, b))` gọi accessor tĩnh.
D. `Line(Point[x,y], Point[a,b])` dùng cú pháp array.
Đáp án đúng: A

Câu 28. Trong `case Point(var x, var y) -> ...`, compiler suy luận kiểu của x và y ra sao?
A. Cả hai có kiểu Integer vì int bị boxing khi match.
B. Cả hai có kiểu Number vì pattern không khai báo type.
C. Cả hai có kiểu int theo record component x và y.
D. Cả hai có kiểu Object do var chỉ dùng cho reference.
Đáp án đúng: C

Câu 29. Với `record Wrapper(Point item) {}`, object `new Wrapper(null)` có match `Wrapper(Point(var x, var y))` không?
A. Không, vì record pattern không được lồng trong Wrapper.
B. Có, record pattern tự dựng Point(0,0) để tiếp tục.
C. Không, nested Point pattern không khớp với null.
D. Có, hai biến x và y được gán null từ item.
Đáp án đúng: C

Câu 30. Type pattern trong record pattern có thể được dùng vào mục đích nào?
A. Chuyển mọi record component thành public mutable field.
B. Dùng component accessors để tách dữ liệu và bind biến.
C. Thay đổi trường private final của record khi pattern match.
D. Gọi constructor record rồi lấy dữ liệu để so sánh.
Đáp án đúng: B

Câu 31. Với `Object obj`, biểu thức `obj instanceof List<?> xs` có hợp lệ trên Java 21 không?
A. Không hợp lệ vì instanceof không hỗ trợ bất kỳ generic type.
B. Hợp lệ vì List<?> là dạng reifiable để dùng với instanceof.
C. Không hợp lệ vì biến pattern xs phải có kiểu `List<Object>`.
D. Hợp lệ vì JVM kiểm tra kiểu generic của mọi phần tử lúc chạy.
Đáp án đúng: B

Câu 32. Với `Object obj`, tại sao `obj instanceof List<String> xs` bị từ chối khi biên dịch?
A. Pattern variable xs không được bind nếu type argument là String.
B. Java 21 cấm kết hợp instanceof với mọi parameterized type.
C. `List<String>` không reifiable khi dùng với instanceof.
D. List cần record pattern mới kiểm tra được ở runtime.
Đáp án đúng: C
